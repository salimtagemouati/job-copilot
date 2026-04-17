"""
Interview prep generator — MODULE 7 (interview_prep).

Generates tailored Q&A. Uses Tavily for company research.
Red flags = the gaps the interviewer will probe hardest.
Sample answers reference Salim's real projects ONLY.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import re
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from models.schemas import ParsedJob, FitScore, InterviewPrep
from utils.llm import call_llm, LLMFailureException
from config import settings
from utils.logger import get_logger

logger = get_logger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_jinja_env = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), autoescape=False)


def _render_prompt(template_name: str, **kwargs) -> str:
    template = _jinja_env.get_template(template_name)
    return template.render(**kwargs)


def _get_company_research(job: ParsedJob) -> str:
    """Fetches company research via Tavily, returns empty string on failure."""
    try:
        from ingestion.tavily_search import get_company_research
        return get_company_research(job.company, job.role)
    except Exception as e:
        logger.warning(f"[interview_prep] Company research failed: {e}")
        return ""


def generate_interview_prep(job: ParsedJob, score: FitScore) -> InterviewPrep:
    """
    Generates a tailored interview preparation package.

    Includes:
    - 3-5 technical questions specific to the job's stack
    - 2-3 ML/AI conceptual questions if role is AI-related
    - 2 behavioral questions with STAR format sample answers
    - Red flags (gaps) with honest response strategies
    - Company research from Tavily

    Args:
        job: ParsedJob being applied to
        score: FitScore with identified gaps and risk factors

    Returns:
        Validated InterviewPrep instance

    Raises:
        LLMFailureException: If LLM fails after retries

    Example:
        >>> prep = generate_interview_prep(job, score)
        >>> for q in prep.likely_technical:
        ...     print(f"Q: {q}")
        ...     print(f"A: {prep.sample_answers.get(q, 'No sample answer')}")
    """
    logger.info(f"[interview_prep] Generating prep for: {job.company} | {job.role}")

    # Fetch company research from Tavily (non-blocking)
    company_research = _get_company_research(job)

    prompt = _render_prompt(
        "interview_prep.j2",
        job=job.model_dump(),
        score=score.model_dump(),
        company_research=company_research if company_research else None,
    )

    raw = call_llm(prompt, model=settings.model_interview_prep, purpose="interview_prep", max_tokens=3000)
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.warning(f"[interview_prep] JSON parse failed, retrying: {e}")
        retry_prompt = (
            f"Your previous response was incomplete or invalid JSON.\nError: {e}\n\n"
            f"Broken JSON:\n{raw}\n\n"
            "Repair it into a complete, valid JSON object using this exact schema:\n"
            "{\n"
            '  "likely_technical": ["3-5 technical questions"],\n'
            '  "likely_behavioral": ["2-3 behavioral questions"],\n'
            '  "ml_ai_specific": ["AI/ML-specific questions"],\n'
            '  "sample_answers": {"question": "STAR-style answer"},\n'
            '  "red_flags_to_prepare_for": ["risks to address"],\n'
            '  "company_research": "brief research summary"\n'
            "}\n\n"
            "Return ONLY valid JSON. No backticks."
        )
        raw2 = call_llm(retry_prompt, model=settings.model_interview_prep, purpose="interview_prep_retry", max_tokens=3000)
        cleaned2 = re.sub(r"```(?:json)?\s*", "", raw2).replace("```", "").strip()
        data = json.loads(cleaned2)

    prep = InterviewPrep(
        likely_technical=data.get("likely_technical", []),
        likely_behavioral=data.get("likely_behavioral", []),
        ml_ai_specific=data.get("ml_ai_specific", []),
        sample_answers=data.get("sample_answers", {}),
        red_flags_to_prepare_for=data.get("red_flags_to_prepare_for", []),
        company_research=company_research or data.get("company_research"),
    )

    logger.info(
        f"[interview_prep] Done | technical_Qs={len(prep.likely_technical)} | "
        f"behavioral_Qs={len(prep.likely_behavioral)} | "
        f"red_flags={len(prep.red_flags_to_prepare_for)} | "
        f"research={'yes' if prep.company_research else 'none'}"
    )

    return prep


if __name__ == "__main__":
    from models.schemas import Market, Seniority, Verdict

    test_job = ParsedJob(
        company="Hugging Face",
        role="Junior ML Engineer",
        location="Remote (Worldwide)",
        market=Market.remote,
        remote_ok=True,
        language_required="English",
        jd_language="English",
        requirements=[
            "Python",
            "PyTorch or TensorFlow",
            "Transformer models experience",
            "FastAPI or Flask for model serving",
            "0-2 years experience",
        ],
        nice_to_have=["RLHF knowledge", "Docker", "Gradio"],
        tech_stack=["Python", "PyTorch", "Transformers", "FastAPI", "Docker"],
        seniority=Seniority.junior,
        raw_text="Junior ML Engineer at Hugging Face. Remote worldwide. English working language.",
    )

    test_score = FitScore(
        score=62,
        verdict=Verdict.maybe,
        strengths=["Python strong", "FastAPI for model serving matches", "LLM experience via DocuMind"],
        gaps=["No PyTorch experience (used Gemini API, not raw PyTorch)", "No RLHF knowledge", "No Docker"],
        reasoning="Good LLM background but gaps in ML framework fundamentals.",
        risk_factors=["No raw PyTorch/TF training experience", "< 2 years"],
    )

    print("Generating interview prep...")
    try:
        prep = generate_interview_prep(test_job, test_score)
        print(f"\n✅ Technical Qs: {len(prep.likely_technical)}")
        for q in prep.likely_technical[:2]:
            print(f"  - {q}")
        print(f"\n  Red flags to address: {len(prep.red_flags_to_prepare_for)}")
        for rf in prep.red_flags_to_prepare_for[:2]:
            print(f"  - {rf}")
    except Exception as e:
        print(f"❌ Failed: {e}")
