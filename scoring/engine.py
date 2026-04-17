"""
Fit scoring engine — MODULE 3 (scoring).

The most critical module. Scores Salim's fit against a parsed job.
Strictly calibrated — no optimism bias.
Includes anti-inflation validator that re-prompts if score seems inflated.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import re
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from models.schemas import ParsedJob, FitScore, Verdict, Market
from utils.llm import call_llm, LLMFailureException
from utils.logger import get_logger
from config import settings

logger = get_logger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_jinja_env = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), autoescape=False)


def _render_prompt(template_name: str, **kwargs) -> str:
    template = _jinja_env.get_template(template_name)
    return template.render(**kwargs)


def _parse_score_response(raw: str) -> dict:
    """Cleans and parses LLM score response to dict."""
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()
    return json.loads(cleaned)


def _is_inflated(score: int, gaps: list[str], job: ParsedJob) -> bool:
    """
    Anti-inflation check: flags suspiciously high scores.

    Rule: If LLM returns score > 75 AND job has 3+ skills Salim doesn't have,
    the score is likely inflated. Re-prompt once.

    Args:
        score: Proposed score
        gaps: Identified gaps list
        job: The parsed job

    Returns:
        True if score looks inflated
    """
    if score > 75 and len(gaps) >= 3:
        logger.warning(
            f"[scoring] Anti-inflation triggered: score={score} with {len(gaps)} gaps. Re-prompting."
        )
        return True

    # Also flag if role clearly requires 5+ YOE and score is high
    req_text = " ".join(job.requirements).lower()
    years_match = re.search(r"(\d+)\+?\s*years?\s*(of\s*)?(experience|exp)", req_text)
    if years_match and int(years_match.group(1)) >= 5 and score > 40:
        logger.warning(
            f"[scoring] Anti-inflation triggered: role requires {years_match.group(1)}+ YOE, score={score}."
        )
        return True

    return False


def _derive_verdict(score: int) -> Verdict:
    """Derives verdict from score using configured thresholds."""
    if score >= settings.apply_threshold:
        return Verdict.apply
    elif score >= settings.maybe_threshold:
        return Verdict.maybe
    else:
        return Verdict.skip


def score_fit(job: ParsedJob) -> FitScore:
    """
    Scores Salim's fit against a parsed job.

    Strict and realistic — no optimism bias.
    Runs anti-inflation check and re-prompts if needed.
    Always derives verdict from score thresholds (ignores LLM verdict if inconsistent).

    Args:
        job: Validated ParsedJob to score against

    Returns:
        Validated FitScore instance

    Raises:
        LLMFailureException: If LLM fails after retries

    Example:
        >>> job = parse_job(raw_text)
        >>> score = score_fit(job)
        >>> print(f"{score.verdict}: {score.score}/100")
    """
    logger.info(f"[scoring] Scoring: {job.company} | {job.role} | {job.market}")

    prompt = _render_prompt(
        "score_fit.j2",
        job=job.model_dump(),
    )

    # First attempt
    raw = call_llm(prompt, model=settings.model_score_fit, purpose="score_fit", max_tokens=1500)
    try:
        data = _parse_score_response(raw)
    except json.JSONDecodeError as e:
        logger.warning(f"[scoring] JSON parse failed, retrying: {e}")
        retry_prompt = (
            f"Your previous response was incomplete or invalid JSON.\nError: {e}\n\n"
            f"Broken JSON:\n{raw}\n\n"
            "Repair it into a complete, valid JSON object using this exact schema:\n"
            "{\n"
            '  "score": integer 0-100,\n'
            '  "verdict": "Apply" | "Maybe" | "Skip",\n'
            '  "strengths": ["list of specific strengths"],\n'
            '  "gaps": ["list of specific gaps"],\n'
            '  "reasoning": "2-3 sentence explanation",\n'
            '  "location_flag": "string note or null",\n'
            '  "risk_factors": ["list of factors that may cause rejection"],\n'
            '  "germany_filter_passed": true | false | null\n'
            "}\n\n"
            "Return ONLY valid JSON. No backticks."
        )
        raw = call_llm(retry_prompt, model=settings.model_score_fit, purpose="score_fit_retry", max_tokens=1500)
        data = _parse_score_response(raw)

    score_val = int(data.get("score", 50))
    gaps = data.get("gaps", [])

    # Anti-inflation: re-prompt once if triggered
    if _is_inflated(score_val, gaps, job):
        inflation_note = (
            f"\n\n⚠️  CALIBRATION ALERT: Your previous score of {score_val} is too high.\n"
            f"The role has {len(gaps)} identified gaps: {gaps}.\n"
            f"Re-score strictly. A score > 75 with 3+ missing skills is not credible.\n"
            f"Apply the anti-inflation rule and return a lower, honest score.\n\n"
            f"Original job:\n{prompt}"
        )
        raw = call_llm(inflation_note, model=settings.model_score_fit, purpose="score_fit_calibrate", max_tokens=1500)
        try:
            data = _parse_score_response(raw)
        except json.JSONDecodeError:
            logger.warning("[scoring] Calibration re-prompt also failed JSON parse, using original")

        score_val = int(data.get("score", score_val))
        gaps = data.get("gaps", gaps)

    # Always derive verdict from score — don't trust LLM verdict blindly
    correct_verdict = _derive_verdict(score_val)
    llm_verdict = data.get("verdict", correct_verdict.value)
    if llm_verdict != correct_verdict.value:
        logger.warning(
            f"[scoring] LLM verdict '{llm_verdict}' overridden by score {score_val} → '{correct_verdict.value}'"
        )

    # Handle germany_filter_passed
    germany_passed = data.get("germany_filter_passed")
    if job.market != Market.germany:
        germany_passed = None

    fit = FitScore(
        score=score_val,
        verdict=correct_verdict,
        strengths=data.get("strengths", []),
        gaps=gaps,
        reasoning=data.get("reasoning", ""),
        location_flag=data.get("location_flag"),
        risk_factors=data.get("risk_factors", []),
        germany_filter_passed=germany_passed,
    )

    logger.info(
        f"[scoring] Result: {fit.verdict} | score={fit.score} | "
        f"strengths={len(fit.strengths)} | gaps={len(fit.gaps)}"
    )

    return fit


if __name__ == "__main__":
    from models.schemas import Market, Seniority

    # Test with a realistic Morocco AI role
    test_job = ParsedJob(
        company="IntelliFind",
        role="Junior AI Engineer",
        location="Casablanca, Morocco",
        market=Market.morocco,
        remote_ok=True,
        language_required="French",
        jd_language="French",
        requirements=[
            "Python 3.10+",
            "FastAPI or Flask",
            "LLM integration experience",
            "RAG pipeline design",
            "0-2 years experience",
        ],
        nice_to_have=["Docker", "AWS basics", "LangChain"],
        tech_stack=["Python", "FastAPI", "OpenAI API", "PostgreSQL"],
        seniority=Seniority.junior,
        visa_sponsorship=None,
        salary_range=None,
        raw_text="Junior AI Engineer role at IntelliFind Casablanca. Python FastAPI LLMs required.",
    )

    print("Scoring test job...")
    try:
        score = score_fit(test_job)
        print(f"\n✅ Score: {score.score}/100 → {score.verdict}")
        print(f"  Strengths: {score.strengths}")
        print(f"  Gaps: {score.gaps}")
        print(f"  Reasoning: {score.reasoning}")
        print(f"  Risks: {score.risk_factors}")
    except Exception as e:
        print(f"❌ Scoring failed: {e}")
