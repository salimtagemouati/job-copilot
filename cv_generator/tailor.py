"""
CV tailoring engine — MODULE 5 (cv_generator).

Hard constraint: Only reframes existing experience.
Never adds skills, tools, or projects that don't exist in Salim's profile.
If a required skill is missing → flags it in ats_keywords as "MISSING: skill".
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import re
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from models.schemas import ParsedJob, TailoredCV
from utils.llm import call_llm, LLMFailureException
from config import settings
from utils.logger import get_logger

logger = get_logger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_jinja_env = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), autoescape=False)


def _render_prompt(template_name: str, **kwargs) -> str:
    template = _jinja_env.get_template(template_name)
    return template.render(**kwargs)


def tailor_cv(job: ParsedJob) -> TailoredCV:
    """
    Tailors Salim's CV for a specific job.

    Reorders and rewrites existing experience using the JD's exact verbs
    and keywords wherever truthfully applicable.
    Flags any required skills missing from Salim's real profile.
    Never fabricates experience, tools, or projects.

    Args:
        job: ParsedJob to tailor the CV for

    Returns:
        Validated TailoredCV instance

    Raises:
        LLMFailureException: If LLM fails after retries

    Example:
        >>> cv = tailor_cv(job)
        >>> print(cv.summary)
        >>> print("ATS keywords:", cv.ats_keywords)
        >>> missing = [k for k in cv.ats_keywords if k.startswith("MISSING:")]
        >>> print("Missing skills:", missing)
    """
    logger.info(f"[cv_tailor] Tailoring CV for: {job.company} | {job.role}")

    prompt = _render_prompt("tailor_cv.j2", job=job.model_dump())

    raw = call_llm(prompt, model=settings.model_tailor_cv, purpose="tailor_cv", max_tokens=3000)
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.warning(f"[cv_tailor] JSON parse failed, retrying: {e}")
        retry_prompt = (
            f"Your previous response was incomplete or invalid JSON.\nError: {e}\n\n"
            f"Broken JSON:\n{raw}\n\n"
            "Repair it into a complete, valid JSON object using this exact schema:\n"
            "{\n"
            '  "summary": "2-3 sentence JD-aligned summary",\n'
            '  "experience": [{"title": "...", "company": "...", "duration": "...", "bullets": ["..."]}],\n'
            '  "projects": [{"name": "...", "stack": ["..."], "description": "...", "highlights": ["..."]}],\n'
            '  "skills": ["real skills only"],\n'
            '  "education": [{"degree": "...", "institution": "...", "year": "...", "notes": "..."}],\n'
            '  "ats_keywords": ["keywords or MISSING: skill"]\n'
            "}\n\n"
            "Return ONLY valid JSON. No backticks."
        )
        raw2 = call_llm(retry_prompt, model=settings.model_tailor_cv, purpose="tailor_cv_retry", max_tokens=3000)
        cleaned2 = re.sub(r"```(?:json)?\s*", "", raw2).replace("```", "").strip()
        data = json.loads(cleaned2)

    cv = TailoredCV(
        summary=data.get("summary", ""),
        experience=data.get("experience", []),
        projects=data.get("projects", []),
        skills=data.get("skills", []),
        education=data.get("education", []),
        ats_keywords=data.get("ats_keywords", []),
    )

    missing = [k for k in cv.ats_keywords if k.lower().startswith("missing:")]
    logger.info(
        f"[cv_tailor] CV tailored | ATS keywords: {len(cv.ats_keywords)} | "
        f"Missing skills flagged: {len(missing)}"
    )
    if missing:
        logger.warning(f"[cv_tailor] Missing skills (will NOT appear in CV): {missing}")

    return cv


if __name__ == "__main__":
    from models.schemas import Market, Seniority

    test_job = ParsedJob(
        company="Lydia Solutions",
        role="Junior AI Engineer",
        location="Remote (EU)",
        market=Market.remote,
        remote_ok=True,
        language_required="English",
        jd_language="English",
        requirements=[
            "Python 3.10+",
            "FastAPI or Flask",
            "LLM/RAG pipeline experience",
            "Vector store knowledge (FAISS, Pinecone)",
            "0-2 years experience",
        ],
        nice_to_have=["Docker", "LangChain", "AWS"],
        tech_stack=["Python", "FastAPI", "OpenAI API", "FAISS", "PostgreSQL"],
        seniority=Seniority.junior,
        visa_sponsorship=None,
        salary_range="€35,000 – €45,000",
        raw_text="Junior AI Engineer at Lydia Solutions. English working language. Remote EU.",
    )

    print("Tailoring CV...")
    try:
        cv = tailor_cv(test_job)
        print(f"\n✅ CV tailored:")
        print(f"  Summary: {cv.summary[:120]}...")
        print(f"  Projects: {[p.get('name') for p in cv.projects]}")
        print(f"  ATS keywords: {cv.ats_keywords[:8]}")
        missing = [k for k in cv.ats_keywords if k.startswith("MISSING:")]
        if missing:
            print(f"  ⚠️  Missing skills: {missing}")
    except Exception as e:
        print(f"❌ CV tailoring failed: {e}")
