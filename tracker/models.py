"""
SQLModel table definitions for the Application Tracker — MODULE 8a.

Single table: Application
Tracks every job Salim applies to or considers applying to.
jd_hash (SHA256) is the dedup key — prevents logging the same JD twice.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field


class Application(SQLModel, table=True):
    """
    Persisted record of one job application or evaluation.

    Created automatically when verdict is Apply or Maybe.
    Never created for Skip verdicts (unless user overrides).
    """

    id: Optional[int] = Field(default=None, primary_key=True)

    # ── Job identity ──────────────────────────────────────────────────────────
    company: str = Field(index=True, description="Company name")
    role: str = Field(description="Job title")
    market: str = Field(index=True, description="morocco / germany / canada / remote / other")
    location: str = Field(default="", description="City and country")
    source_url: str = Field(default="", description="Original job posting URL")

    # ── Scoring results ───────────────────────────────────────────────────────
    score: int = Field(description="Fit score 0-100")
    verdict: str = Field(index=True, description="Apply / Maybe / Skip")

    # ── Application lifecycle ─────────────────────────────────────────────────
    status: str = Field(
        default="Applied",
        index=True,
        description="Applied / Interview / Offer / Rejected / Ghosted",
    )
    applied_date: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the application was logged",
    )
    last_updated: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Last status change timestamp",
    )

    # ── Metadata ──────────────────────────────────────────────────────────────
    notes: str = Field(default="", description="Free-text notes from Salim")
    jd_hash: str = Field(
        index=True,
        unique=True,
        description="SHA256 of raw JD text — unique dedup key",
    )
    pdf_path: str = Field(default="", description="Path to the generated CV PDF")

    class Config:
        # Allow mutation (for status updates)
        arbitrary_types_allowed = True


if __name__ == "__main__":
    # Smoke test: create an in-memory Application instance (no DB needed)
    app = Application(
        company="Zalando",
        role="Junior ML Engineer",
        market="germany",
        location="Berlin, Germany",
        source_url="https://jobs.zalando.com/123",
        score=74,
        verdict="Apply",
        status="Applied",
        jd_hash="abc123def456" * 4,
        pdf_path="outputs/pdfs/Zalando_Junior_ML_Engineer_2025-04-14.pdf",
        notes="English-first team. Visa sponsorship mentioned.",
    )

    print("✅ Application model:")
    print(f"  {app.company} | {app.role} | score={app.score} | status={app.status}")
    print(f"  market={app.market} | verdict={app.verdict}")
    print(f"  hash={app.jd_hash[:16]}...")
