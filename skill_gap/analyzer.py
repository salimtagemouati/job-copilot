"""
Skill gap analyzer — MODULE 4 (skill_gap).

Always runs after scoring — even for Skip verdicts.
Tells Salim exactly what to learn to close the gap.
Resources must be specific (course name, not "take a course").
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import re
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from models.schemas import ParsedJob, FitScore, SkillGap
from utils.llm import call_llm, LLMFailureException
from config import settings
from utils.logger import get_logger

logger = get_logger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_jinja_env = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), autoescape=False)


def _render_prompt(template_name: str, **kwargs) -> str:
    template = _jinja_env.get_template(template_name)
    return template.render(**kwargs)


def analyze_gaps(job: ParsedJob, score: FitScore) -> SkillGap:
    """
    Analyzes skill gaps between Salim's profile and the job requirements.

    Always runs — even for Skip verdicts. A Skip job still teaches Salim
    what he'd need to learn to become competitive in that direction.

    Resources are always specific: course name + platform + hours estimate.
    Never generic ("learn Docker" → "Docker: Play With Docker free labs, ~4h").

    Args:
        job: ParsedJob being evaluated
        score: FitScore from scoring engine (gaps already identified)

    Returns:
        Validated SkillGap instance with actionable learning plan

    Raises:
        LLMFailureException: If LLM fails after retries

    Example:
        >>> gaps = analyze_gaps(job, score)
        >>> for r in gaps.resources:
        ...     print(r)
    """
    logger.info(
        f"[gap_analyzer] Analyzing gaps for: {job.company} | {job.role} | "
        f"score={score.score} verdict={score.verdict}"
    )

    prompt = _render_prompt(
        "skill_gap.j2",
        job=job.model_dump(),
        score=score.model_dump(),
    )

    raw = call_llm(prompt, model=settings.model_skill_gap, purpose="skill_gap", max_tokens=1500)

    cleaned = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.warning(f"[gap_analyzer] JSON parse failed, retrying: {e}")
        retry_prompt = (
            f"Your previous response was incomplete or invalid JSON.\nError: {e}\n\n"
            f"Broken JSON:\n{raw}\n\n"
            "Repair it into a complete, valid JSON object using this exact schema:\n"
            "{\n"
            '  "missing_skills": ["list of specific missing skills"],\n'
            '  "learning_priority": ["skills ordered highest ROI first"],\n'
            '  "resources": ["specific course or doc names with platform"],\n'
            '  "estimated_effort": "realistic time estimate",\n'
            '  "score_impact": "how much the score would improve"\n'
            "}\n\n"
            "Return ONLY valid JSON. No backticks."
        )
        raw2 = call_llm(retry_prompt, model=settings.model_skill_gap, purpose="skill_gap_retry", max_tokens=1500)
        cleaned2 = re.sub(r"```(?:json)?\s*", "", raw2).replace("```", "").strip()
        data = json.loads(cleaned2)

    gap = SkillGap(
        missing_skills=data.get("missing_skills", []),
        learning_priority=data.get("learning_priority", []),
        resources=data.get("resources", []),
        estimated_effort=data.get("estimated_effort", "Unknown"),
        score_impact=data.get("score_impact", "Unknown"),
    )

    logger.info(
        f"[gap_analyzer] Found {len(gap.missing_skills)} gaps | "
        f"top priority: {gap.learning_priority[:2]} | effort: {gap.estimated_effort}"
    )

    return gap


if __name__ == "__main__":
    from models.schemas import Market, Seniority, Verdict

    test_job = ParsedJob(
        company="DataLayer",
        role="ML Platform Engineer",
        location="Berlin, Germany",
        market=Market.germany,
        remote_ok=True,
        language_required="English",
        jd_language="English",
        requirements=[
            "Python",
            "MLflow or similar experiment tracking",
            "AWS SageMaker or GCP Vertex AI",
            "Kubernetes basics",
            "3+ years experience",
        ],
        nice_to_have=["Spark", "Terraform"],
        tech_stack=["Python", "MLflow", "AWS SageMaker", "Kubernetes", "Docker"],
        seniority=Seniority.mid,
        visa_sponsorship=True,
        salary_range="€55,000 – €75,000",
        raw_text="ML Platform Engineer at DataLayer Berlin. English working language. International team.",
    )

    test_score = FitScore(
        score=38,
        verdict=Verdict.skip,
        strengths=["Python strong", "ML background"],
        gaps=["No MLflow", "No AWS SageMaker", "No Kubernetes", "3+ YOE required"],
        reasoning="Too many infrastructure gaps for current level.",
        risk_factors=["< 2 years experience", "No cloud certs"],
    )

    print("Analyzing gaps...")
    try:
        gap = analyze_gaps(test_job, test_score)
        print(f"\n✅ Missing: {gap.missing_skills}")
        print(f"  Priority: {gap.learning_priority}")
        print(f"  Effort: {gap.estimated_effort}")
        print(f"  Impact: {gap.score_impact}")
        print(f"  Resources:")
        for r in gap.resources:
            print(f"    - {r}")
    except Exception as e:
        print(f"❌ Gap analysis failed: {e}")
