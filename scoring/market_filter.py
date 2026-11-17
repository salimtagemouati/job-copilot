"""
Market pre-filters for AI Job Copilot.

Runs BEFORE the LLM scoring engine.
If a job fails pre-filtering, skip the entire pipeline immediately.

Key rule: Salim does not speak German — any German-language-required
role must be caught here and rejected cleanly.
"""

from models.schemas import ParsedJob, Market
from utils.logger import get_logger

logger = get_logger(__name__)

# ── Germany auto-reject patterns ──────────────────────────────────────────────
GERMANY_REJECT_PHRASES = [
    "deutschkenntnisse erforderlich",
    "deutschkenntnisse vorausgesetzt",
    "muttersprachler",
    "c1 deutsch",
    "c2 deutsch",
    "fließend deutsch",
    "fließende deutschkenntnisse",
    "sehr gute deutschkenntnisse",
    "gute deutschkenntnisse",
    "deutsche sprache",
    "deutsch auf muttersprachlichem niveau",
]

# ── Germany pass phrases — at least one required ──────────────────────────────
GERMANY_PASS_PHRASES = [
    "english working language",
    "english is the working language",
    "english-speaking team",
    "international team",
    "english-first",
    "working language is english",
    "our language is english",
    "business language is english",
    "we work in english",
]

# ── Germany bonus flags (noted in score, don't gate on these alone) ───────────
GERMANY_BONUS_PHRASES = [
    "visa sponsorship",
    "relocation support",
    "relocation package",
    "blue card",
    "eu blue card",
    "niederlassungserlaubnis",
    "work permit",
    "we sponsor",
]

# ── Canada pass phrases ───────────────────────────────────────────────────────
CANADA_PASS_PHRASES = [
    "open to international applicants",
    "lmia",
    "work permit sponsorship",
    "we sponsor work permits",
    "open to sponsoring",
]


def _normalize(text: str) -> str:
    """Lowercase + strip for phrase matching."""
    return text.lower().strip()


def check_germany_eligibility(job: ParsedJob) -> tuple[bool, str]:
    """
    Checks if a Germany job is eligible for Salim to apply.

    Since Salim has no German language skills, German-required roles
    are rejected immediately before any LLM scoring runs.

    Args:
        job: ParsedJob to evaluate

    Returns:
        (is_eligible, reason) tuple.
        If is_eligible is False, skip the entire pipeline.

    Example:
        >>> eligible, reason = check_germany_eligibility(job)
        >>> if not eligible:
        ...     print(f"Skipping: {reason}")
    """
    combined_text = _normalize(job.raw_text + " " + job.role + " " + job.location)
    jd_lang = _normalize(job.jd_language)

    if any(phrase in combined_text for phrase in ("german required", "german is required", "fluent german required", "german proficiency required")) or _normalize(job.language_required) in {"german", "english and german", "german and english"}:
        return False, "German language proficiency is required."

    # ── Auto-reject: JD is entirely in German with no English signals ─────────
    if jd_lang == "german":
        # Check if any English pass phrase redeems it
        has_english_signal = any(p in combined_text for p in GERMANY_PASS_PHRASES)
        if not has_english_signal:
            reason = (
                f"JD written in German (jd_language='{job.jd_language}') "
                "with no English working language signal. "
                "Salim does not speak German."
            )
            logger.warning(f"[GermanyFilter] AUTO-REJECT: {reason}")
            return False, reason

    # ── Auto-reject: explicit German language requirement phrases ─────────────
    for phrase in GERMANY_REJECT_PHRASES:
        if phrase in combined_text:
            reason = (
                f"Found German language requirement: '{phrase}'. "
                "Salim does not meet this requirement."
            )
            logger.warning(f"[GermanyFilter] AUTO-REJECT: {reason}")
            return False, reason

    # ── Must pass: at least one English-working-language signal ───────────────
    has_pass_signal = any(p in combined_text for p in GERMANY_PASS_PHRASES)

    # If JD is in English and no reject phrases found, it passes implicitly
    if jd_lang == "english":
        has_pass_signal = True

    if not has_pass_signal:
        reason = (
            "No English working language signal found "
            "(no 'English working language', 'international team', etc.). "
            "Cannot confirm Salim can work in this role without German."
        )
        logger.warning(f"[GermanyFilter] BORDERLINE REJECT: {reason}")
        return False, reason

    # ── Check for bonus flags (informational only) ────────────────────────────
    bonuses = [p for p in GERMANY_BONUS_PHRASES if p in combined_text]
    bonus_note = f" Bonus flags: {bonuses}" if bonuses else ""

    reason = f"Passed Germany filter. JD language: {job.jd_language}.{bonus_note}"
    logger.info(f"[GermanyFilter] PASS: {reason}")
    return True, reason


def get_germany_bonus_flags(job: ParsedJob) -> list[str]:
    """
    Returns list of visa/relocation bonus phrases found in the JD.
    Used by scoring engine to add bonus points.

    Args:
        job: ParsedJob to check

    Returns:
        List of matched bonus phrases
    """
    combined = _normalize(job.raw_text)
    return [p for p in GERMANY_BONUS_PHRASES if p in combined]


def check_canada_eligibility(job: ParsedJob) -> tuple[bool, str]:
    """
    Checks if a Canada job is eligible — must have work permit sponsorship signal.

    Args:
        job: ParsedJob to evaluate

    Returns:
        (is_eligible, reason) tuple
    """
    combined = _normalize(job.raw_text)
    if job.visa_sponsorship is False or any(phrase in combined for phrase in (
        "no visa sponsorship", "no sponsorship", "cannot sponsor", "do not sponsor",
        "not offer sponsorship", "sponsorship is not available", "no lmia",
    )):
        return False, "The posting excludes sponsorship."
    has_signal = any(p in combined for p in CANADA_PASS_PHRASES)

    if not has_signal:
        reason = (
            "No work permit / sponsorship signal found for Canada role. "
            "Salim needs sponsorship to work in Canada."
        )
        logger.warning(f"[CanadaFilter] SKIP: {reason}")
        return False, reason

    logger.info(f"[CanadaFilter] PASS: Work permit signal found.")
    return True, "Passed Canada filter — work permit sponsorship signal found."


def run_market_filter(job: ParsedJob) -> tuple[bool, str]:
    """
    Routes to the appropriate market filter based on job.market.
    Morocco and Remote pass automatically.

    Args:
        job: ParsedJob to evaluate

    Returns:
        (is_eligible, reason) tuple
    """
    if job.market == Market.germany:
        return check_germany_eligibility(job)
    elif job.market == Market.canada:
        return check_canada_eligibility(job)
    elif job.market in (Market.morocco, Market.remote, Market.other):
        return True, f"Market '{job.market}' passes automatically."
    else:
        logger.warning(f"[MarketFilter] Unknown market '{job.market}', passing by default.")
        return True, f"Unknown market '{job.market}' — passed by default."


if __name__ == "__main__":
    from models.schemas import Market

    # Test 1: German-required role — should reject
    job_de_reject = ParsedJob(
        company="German Corp",
        role="AI Engineer",
        location="Berlin, Germany",
        market=Market.germany,
        remote_ok=False,
        language_required="German",
        jd_language="German",
        requirements=["C1 Deutsch erforderlich", "Python"],
        nice_to_have=[],
        tech_stack=["Python"],
        seniority="junior",
        raw_text="Wir suchen einen AI Engineer. Deutschkenntnisse erforderlich. C1 Deutsch.",
    )

    eligible, reason = check_germany_eligibility(job_de_reject)
    print(f"Test 1 (should REJECT): eligible={eligible}\n  → {reason}\n")

    # Test 2: English-language Germany role — should pass
    job_de_pass = ParsedJob(
        company="Zalando",
        role="Junior ML Engineer",
        location="Berlin, Germany",
        market=Market.germany,
        remote_ok=True,
        language_required="English",
        jd_language="English",
        requirements=["Python", "ML experience"],
        nice_to_have=["German is a plus"],
        tech_stack=["Python", "TensorFlow"],
        seniority="junior",
        raw_text=(
            "Zalando is looking for a Junior ML Engineer. "
            "English is the working language. "
            "International team. Visa sponsorship available."
        ),
    )

    eligible, reason = check_germany_eligibility(job_de_pass)
    print(f"Test 2 (should PASS): eligible={eligible}\n  → {reason}\n")

    # Test 3: Morocco — always pass
    job_ma = ParsedJob(
        company="OCP Group",
        role="Data Scientist",
        location="Casablanca, Morocco",
        market=Market.morocco,
        remote_ok=False,
        language_required="French",
        jd_language="French",
        requirements=["Python", "ML"],
        nice_to_have=[],
        tech_stack=["Python"],
        seniority="junior",
        raw_text="Nous recherchons un Data Scientist...",
    )
    eligible, reason = run_market_filter(job_ma)
    print(f"Test 3 (Morocco, should PASS): eligible={eligible}\n  → {reason}")
