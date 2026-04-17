"""
Job description parser — MODULE 2 (ingestion).

Parses raw JD text into a validated ParsedJob using the LLM.
Primary input: raw pasted text (always works, zero dependencies).
Secondary input: URL → Tavily fetch (when available).
Handles: vague JDs, mixed-language JDs, missing salary, duplicate detection.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from models.schemas import ParsedJob, Market, Seniority
from utils.llm import call_llm, call_llm_structured, LLMFailureException
from utils.validators import hash_text
from utils.logger import get_logger
from config import settings

logger = get_logger(__name__)

# Jinja2 environment pointing at /prompts/
_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_PROMPTS_DIR)),
    autoescape=False,
)


def _render_prompt(template_name: str, **kwargs) -> str:
    """Renders a Jinja2 prompt template with the given context."""
    template = _jinja_env.get_template(template_name)
    return template.render(**kwargs)


def _infer_market(location: str, jd_language: str, language_required: str) -> Market:
    """
    Best-effort market inference if the LLM didn't return a valid market.

    Args:
        location: Location string from parsed job
        jd_language: Language the JD is written in
        language_required: Working language required

    Returns:
        Most likely Market enum value
    """
    loc = location.lower()
    if any(w in loc for w in ["morocco", "maroc", "casablanca", "rabat", "fes", "fez", "tanger"]):
        return Market.morocco
    if any(w in loc for w in ["germany", "deutschland", "berlin", "munich", "münchen", "hamburg", "frankfurt"]):
        return Market.germany
    if any(w in loc for w in ["canada", "montreal", "toronto", "vancouver"]):
        return Market.canada
    if any(w in loc for w in ["remote", "worldwide", "anywhere", "global"]):
        return Market.remote
    if jd_language.lower() == "german":
        return Market.germany
    return Market.other


def parse_job(raw_text: str, source_url: str | None = None) -> ParsedJob:
    """
    Parses a raw job description into a validated ParsedJob using the LLM.

    Always validates output with Pydantic.
    Infers market from location + language signals.
    Never hallucinates salary or visa sponsorship.

    Args:
        raw_text: Raw job description text (pasted or fetched)
        source_url: Optional source URL for audit trail

    Returns:
        Validated ParsedJob instance

    Raises:
        LLMFailureException: If LLM fails after retries
        ValidationError: If Pydantic validation fails after retries

    Example:
        >>> job = parse_job("We are hiring a Junior ML Engineer in Berlin...")
        >>> print(job.company, job.role, job.score)
    """
    if not raw_text or not raw_text.strip():
        raise ValueError("raw_text cannot be empty")

    logger.info(f"[parser] Parsing JD ({len(raw_text)} chars), url={source_url or 'none'}")

    # Render the prompt template
    prompt = _render_prompt(
        "parse_job.j2",
        raw_text=raw_text.strip(),
        source_url=source_url,
    )

    # Call LLM and parse into a dict first (ParsedJob needs raw_text injected)
    import json, re

    raw_response = call_llm(prompt, model=settings.model_parse_job, purpose="parse_job", max_tokens=2000)

    # Clean and parse JSON
    cleaned = re.sub(r"```(?:json)?\s*", "", raw_response).replace("```", "").strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.warning(f"[parser] JSON decode failed, retrying: {e}")
        retry_prompt = (
            f"Your previous response was not valid JSON.\n"
            f"Error: {e}\n\nOriginal request:\n{prompt}\n\n"
            f"Return ONLY valid JSON. No preamble. No backticks."
        )
        raw_response = call_llm(retry_prompt, model=settings.model_parse_job, purpose="parse_job_retry", max_tokens=2000)
        cleaned = re.sub(r"```(?:json)?\s*", "", raw_response).replace("```", "").strip()
        data = json.loads(cleaned)

    # Always inject raw_text and source_url (LLM may truncate)
    data["raw_text"] = raw_text
    data["source_url"] = source_url

    language_required = data.get("language_required")
    if isinstance(language_required, list):
        data["language_required"] = " / ".join(str(item) for item in language_required if item)
    elif language_required is None:
        data["language_required"] = "Unknown"
    elif not isinstance(language_required, str):
        data["language_required"] = str(language_required)

    # Sanitize market — fall back to inference if invalid
    try:
        Market(data.get("market", "other"))
    except ValueError:
        data["market"] = _infer_market(
            data.get("location", ""),
            data.get("jd_language", ""),
            data.get("language_required", ""),
        ).value
        logger.warning(f"[parser] Invalid market from LLM, inferred: {data['market']}")

    # Sanitize seniority
    try:
        Seniority(data.get("seniority", "unknown"))
    except ValueError:
        data["seniority"] = "unknown"

    # Parse and validate
    job = ParsedJob.model_validate(data)

    jd_hash = hash_text(raw_text)
    logger.info(
        f"[parser] Parsed: {job.company} | {job.role} | {job.market} | "
        f"seniority={job.seniority} | hash={jd_hash[:12]}..."
    )

    return job


if __name__ == "__main__":
    sample_jd = """
    Company: Lydia Solutions (Fintech, Paris/Remote)

    Role: Junior AI Engineer — Conversational AI Team

    We are building the next generation of AI-powered financial assistants.
    Our team works in English. International candidates welcome.

    Requirements:
    - Python 3.10+, FastAPI or Flask
    - Experience with LLMs (OpenAI, Anthropic, or similar)
    - RAG pipeline design and implementation
    - Basic SQL (PostgreSQL preferred)
    - 0-2 years experience

    Nice to have:
    - LangChain or custom orchestration
    - Vector stores (Pinecone, FAISS, Weaviate)
    - Docker / basic cloud deployment

    Location: Remote (EU preferred, Morocco/Africa also considered)
    Salary: €35,000 – €45,000 / year
    Language: English is the working language
    """

    print("Parsing sample JD...")
    try:
        job = parse_job(sample_jd)
        print(f"\n✅ Parsed job:")
        print(f"  Company: {job.company}")
        print(f"  Role: {job.role}")
        print(f"  Market: {job.market}")
        print(f"  Seniority: {job.seniority}")
        print(f"  Tech stack: {job.tech_stack}")
        print(f"  Remote: {job.remote_ok}")
        print(f"  Visa: {job.visa_sponsorship}")
        print(f"  Salary: {job.salary_range}")
    except Exception as e:
        print(f"❌ Parse failed: {e}")
