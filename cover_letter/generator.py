"""
Cover letter generator — MODULE 6 (cover_letter).

Hard limit: 150-250 words.
Confident, technical, direct tone.
Never uses forbidden phrases. Names company + role in first sentence.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import re
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from models.schemas import ParsedJob, FitScore, TailoredCV, CoverLetter
from utils.llm import call_llm, LLMFailureException
from config import settings
from utils.validators import count_words
from utils.logger import get_logger

logger = get_logger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_jinja_env = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), autoescape=False)

# Forbidden phrases — flag if any appear in output
FORBIDDEN_PHRASES = [
    "i am passionate about",
    "i am excited to",
    "i would be a great fit",
    "dynamic team",
    "fast-paced environment",
    "i have always been",
    "dream company",
    "i am thrilled",
    "i am eager",
]


def _render_prompt(template_name: str, **kwargs) -> str:
    template = _jinja_env.get_template(template_name)
    return template.render(**kwargs)


def _check_forbidden(body: str) -> list[str]:
    """Returns list of forbidden phrases found in the cover letter body."""
    lower = body.lower()
    return [p for p in FORBIDDEN_PHRASES if p in lower]


def generate_cover_letter(
    job: ParsedJob, cv: TailoredCV, score: FitScore
) -> CoverLetter:
    """
    Generates a tailored cover letter for a specific job application.

    Hard limit: 150-250 words (validated and re-prompted if violated).
    Language: matches JD language (French JD → French cover letter).
    Forbidden phrases are detected and flagged.

    Args:
        job: ParsedJob being applied to
        cv: TailoredCV for alignment context
        score: FitScore for strengths context

    Returns:
        Validated CoverLetter instance

    Raises:
        LLMFailureException: If LLM fails after retries

    Example:
        >>> letter = generate_cover_letter(job, cv, score)
        >>> print(f"Subject: {letter.subject_line}")
        >>> print(f"Words: {letter.word_count}")
        >>> print(letter.body)
    """
    logger.info(f"[cover_letter] Generating for: {job.company} | {job.role} | lang={job.jd_language}")

    prompt = _render_prompt(
        "cover_letter.j2",
        job=job.model_dump(),
        cv=cv.model_dump(),
        score=score.model_dump(),
    )

    for attempt in range(2):
        raw = call_llm(
            prompt,
            model=settings.model_cover_letter,
            purpose=f"cover_letter_attempt{attempt+1}",
            max_tokens=1000,
        )
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.warning(f"[cover_letter] JSON parse failed attempt {attempt+1}: {e}")
            prompt = (
                f"Your previous response was incomplete or invalid JSON.\nError: {e}\n\n"
                f"Broken JSON:\n{raw}\n\n"
                "Repair it into a complete, valid JSON object using this exact schema:\n"
                "{\n"
                '  "subject_line": "email subject",\n'
                '  "body": "150-250 word cover letter",\n'
                '  "word_count": integer\n'
                "}\n\n"
                "Return ONLY valid JSON. No backticks."
            )
            continue

        body = data.get("body", "")
        subject = data.get("subject_line", f"Application for {job.role}")
        actual_words = count_words(body)

        # Check word count
        if not (150 <= actual_words <= 250):
            logger.warning(
                f"[cover_letter] Word count {actual_words} outside 150-250. Re-prompting."
            )
            prompt = (
                f"Your cover letter had {actual_words} words. "
                f"It must be EXACTLY 150-250 words.\n"
                f"{'Cut it down' if actual_words > 250 else 'Expand it'}.\n\n"
                f"Original request:\n{prompt}\n\n"
                f"Return ONLY valid JSON with subject_line, body, word_count."
            )
            continue

        # Check forbidden phrases
        forbidden_found = _check_forbidden(body)
        if forbidden_found:
            logger.warning(f"[cover_letter] Forbidden phrases found: {forbidden_found}. Re-prompting.")
            prompt = (
                f"Your cover letter contains forbidden phrases: {forbidden_found}\n"
                f"Remove ALL of these. Rewrite those sentences.\n\n"
                f"Original request:\n{prompt}"
            )
            continue

        letter = CoverLetter(
            subject_line=subject,
            body=body,
            word_count=actual_words,
        )

        logger.info(
            f"[cover_letter] Generated | words={actual_words} | "
            f"subject='{subject[:50]}'"
        )
        return letter

    raise LLMFailureException(
        "[cover_letter] Failed to generate valid cover letter within word limit after 2 attempts."
    )


if __name__ == "__main__":
    from models.schemas import Market, Seniority, Verdict

    test_job = ParsedJob(
        company="Lydia Solutions",
        role="Junior AI Engineer",
        location="Remote (EU)",
        market=Market.remote,
        remote_ok=True,
        language_required="English",
        jd_language="English",
        requirements=["Python", "FastAPI", "LLM/RAG experience"],
        nice_to_have=["Docker", "LangChain"],
        tech_stack=["Python", "FastAPI", "OpenAI API", "FAISS"],
        seniority=Seniority.junior,
        raw_text="Junior AI Engineer. Python FastAPI LLM RAG. Remote EU.",
    )

    test_cv = TailoredCV(
        summary="AI Engineer specializing in RAG pipelines and LLM integration.",
        experience=[],
        projects=[{"name": "DocuMind", "stack": ["FastAPI", "Gemini", "FAISS"], "description": "RAG SaaS", "highlights": []}],
        skills=["Python", "FastAPI", "LLMs"],
        education=[],
        ats_keywords=["RAG", "LLM", "FastAPI"],
    )

    test_score = FitScore(
        score=78,
        verdict=Verdict.apply,
        strengths=["DocuMind directly matches RAG requirement", "FastAPI expertise"],
        gaps=["No Docker"],
        reasoning="Strong technical fit.",
        risk_factors=["< 2 years experience"],
    )

    print("Generating cover letter...")
    try:
        letter = generate_cover_letter(test_job, test_cv, test_score)
        print(f"\n✅ Subject: {letter.subject_line}")
        print(f"   Words: {letter.word_count}")
        print(f"\n{letter.body}")
    except Exception as e:
        print(f"❌ Failed: {e}")
