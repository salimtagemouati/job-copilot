"""
Application configuration via pydantic-settings.

Multi-provider LLM routing:
  - Claude (Anthropic) for quality-critical tasks: scoring, CV, cover letter
  - Gemini Flash (Google) for high-volume tasks: parsing, gaps, interview prep
  - All model assignments overridable via .env — zero code changes needed

Reads from .env file or environment variables.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── API Keys ──────────────────────────────────────────────────────────────
    anthropic_api_key: str
    gemini_api_key: str
    tavily_api_key: str

    # ── Per-task model routing ────────────────────────────────────────────────
    # Provider is inferred from model name prefix:
    #   "claude-"  → Anthropic SDK
    #   "gemini-"  → Google GenAI SDK
    #
    # Quality-critical → Claude Sonnet (same quality as Opus, 5x cheaper)
    model_score_fit: str      = "claude-sonnet-4-20250514"
    model_tailor_cv: str      = "claude-sonnet-4-20250514"
    model_cover_letter: str   = "claude-sonnet-4-20250514"
    # High-volume / structured extraction → Gemini 2.5 Flash (fast + cheap)
    model_parse_job: str      = "gemini-2.5-flash-preview-04-17"
    model_skill_gap: str      = "gemini-2.5-flash-preview-04-17"
    model_interview_prep: str = "gemini-2.5-flash-preview-04-17"

    # ── Fallback ──────────────────────────────────────────────────────────────
    gemini_fallback_model: str = "claude-sonnet-4-20250514"
    enable_fallback: bool = True

    # ── Reliability ───────────────────────────────────────────────────────────
    max_retries: int = 2
    retry_delay_seconds: float = 2.0

    # ── Storage ───────────────────────────────────────────────────────────────
    db_path: str = "job_copilot.db"
    pdf_output_dir: str = "outputs/pdfs"

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: str = "INFO"

    # ── Scoring thresholds ────────────────────────────────────────────────────
    apply_threshold: int = 70
    maybe_threshold: int = 45

    # ── Cost estimates per 1M tokens (logging only) ───────────────────────────
    claude_sonnet_input_cost: float  = 3.00
    claude_sonnet_output_cost: float = 15.00
    gemini_flash_input_cost: float   = 0.15
    gemini_flash_output_cost: float  = 0.60


settings = Settings()

Path(settings.pdf_output_dir).mkdir(parents=True, exist_ok=True)
Path("outputs/html").mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    def _mask(key: str) -> str:
        return f"{key[:14]}..." if key else "[MISSING]"

    print("Config loaded\n")
    print("  API Keys:")
    print(f"    Anthropic : {_mask(settings.anthropic_api_key)}")
    print(f"    Gemini    : {_mask(settings.gemini_api_key)}")
    print(f"    Tavily    : {_mask(settings.tavily_api_key)}")
    print("\n  Model routing:")
    print(f"    parse_job      -> {settings.model_parse_job}")
    print(f"    score_fit      -> {settings.model_score_fit}")
    print(f"    skill_gap      -> {settings.model_skill_gap}")
    print(f"    tailor_cv      -> {settings.model_tailor_cv}")
    print(f"    cover_letter   -> {settings.model_cover_letter}")
    print(f"    interview_prep -> {settings.model_interview_prep}")
    print(f"\n  Fallback: {'on' if settings.enable_fallback else 'off'} -> {settings.gemini_fallback_model}")
