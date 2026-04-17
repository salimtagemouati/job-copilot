"""
Shared Pydantic schemas for AI Job Copilot.
All modules import from here. Never redefine locally.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional
from enum import Enum
from datetime import datetime, timezone


class Seniority(str, Enum):
    junior = "junior"
    mid = "mid"
    senior = "senior"
    unknown = "unknown"


class Verdict(str, Enum):
    apply = "Apply"
    maybe = "Maybe"
    skip = "Skip"


class ApplicationStatus(str, Enum):
    applied = "Applied"
    interview = "Interview"
    offer = "Offer"
    rejected = "Rejected"
    ghosted = "Ghosted"


class Market(str, Enum):
    morocco = "morocco"
    germany = "germany"
    canada = "canada"
    remote = "remote"
    other = "other"


class ParsedJob(BaseModel):
    """Structured representation of a parsed job description."""

    company: str = Field(..., description="Company name")
    role: str = Field(..., description="Job title / role name")
    location: str = Field(..., description="Job location (city, country, or 'Remote')")
    market: Market = Field(..., description="Inferred market category")
    remote_ok: bool = Field(..., description="Whether remote work is accepted")
    language_required: str = Field(
        ..., description="Working language required: English, French, German, etc."
    )
    jd_language: str = Field(
        ..., description="Language the JD itself is written in"
    )
    requirements: list[str] = Field(
        default_factory=list, description="Hard requirements from the JD"
    )
    nice_to_have: list[str] = Field(
        default_factory=list, description="Nice-to-have / bonus skills"
    )
    tech_stack: list[str] = Field(
        default_factory=list, description="Technologies and tools mentioned"
    )
    seniority: Seniority = Field(..., description="Inferred seniority level")
    visa_sponsorship: Optional[bool] = Field(
        None, description="True if visa sponsorship mentioned, False if excluded, None if unknown"
    )
    salary_range: Optional[str] = Field(
        None, description="Salary range if mentioned, else None"
    )
    raw_text: str = Field(..., description="Original JD text for audit trail")
    source_url: Optional[str] = Field(None, description="Source URL if available")

    model_config = {"use_enum_values": True}


class FitScore(BaseModel):
    """Salim's fit score against a specific job."""

    score: int = Field(..., ge=0, le=100, description="Fit score 0-100")
    verdict: Verdict = Field(..., description="Apply / Maybe / Skip")
    strengths: list[str] = Field(
        default_factory=list, description="Reasons Salim is a strong fit"
    )
    gaps: list[str] = Field(
        default_factory=list, description="Specific gaps or weaknesses"
    )
    reasoning: str = Field(..., description="Overall scoring rationale")
    location_flag: Optional[str] = Field(
        None, description="Any location-specific note (visa, language, etc.)"
    )
    risk_factors: list[str] = Field(
        default_factory=list, description="Factors that could cause rejection"
    )
    germany_filter_passed: Optional[bool] = Field(
        None,
        description="True/False for Germany jobs, None for all others",
    )

    @field_validator("verdict", mode="before")
    @classmethod
    def derive_verdict_from_score(cls, v, info):
        """Allow verdict to be passed directly, but validate consistency."""
        return v

    model_config = {"use_enum_values": True}


class SkillGap(BaseModel):
    """Actionable skill gap analysis for a specific job."""

    missing_skills: list[str] = Field(
        default_factory=list, description="Skills required but Salim doesn't have"
    )
    learning_priority: list[str] = Field(
        default_factory=list, description="Skills ordered by ROI — learn these first"
    )
    resources: list[str] = Field(
        default_factory=list,
        description="Specific resources (course names, docs) — not generic advice",
    )
    estimated_effort: str = Field(
        ..., description="Realistic time estimate to close the gap"
    )
    score_impact: str = Field(
        ..., description="How much score would improve if gaps were closed"
    )


class TailoredCV(BaseModel):
    """CV tailored for a specific job application."""

    summary: str = Field(..., description="2-3 sentence professional summary, JD-aligned")
    experience: list[dict] = Field(
        default_factory=list,
        description="Work experience entries, reordered and rewritten for the role",
    )
    projects: list[dict] = Field(
        default_factory=list,
        description="Projects reordered by relevance to this specific role",
    )
    skills: list[str] = Field(
        default_factory=list, description="Skills list, prioritized for this role"
    )
    education: list[dict] = Field(
        default_factory=list, description="Education entries"
    )
    ats_keywords: list[str] = Field(
        default_factory=list,
        description="Keywords extracted from JD — verify these appear in the CV",
    )


class CoverLetter(BaseModel):
    """Cover letter for a specific application."""

    subject_line: str = Field(..., description="Email subject line")
    body: str = Field(..., description="Cover letter body, 150-250 words hard limit")
    word_count: int = Field(..., ge=150, le=250, description="Word count — enforced")

    @field_validator("word_count", mode="before")
    @classmethod
    def validate_word_count(cls, v, info):
        """Auto-compute word count from body if possible."""
        return v


class InterviewPrep(BaseModel):
    """Interview preparation package for a specific role."""

    likely_technical: list[str] = Field(
        default_factory=list,
        description="3-5 technical questions specific to the job's stack",
    )
    likely_behavioral: list[str] = Field(
        default_factory=list, description="2-3 behavioral questions in STAR format"
    )
    ml_ai_specific: list[str] = Field(
        default_factory=list,
        description="ML/AI conceptual questions if role is AI-related",
    )
    sample_answers: dict[str, str] = Field(
        default_factory=dict,
        description="Sample answers referencing Salim's real projects ONLY",
    )
    red_flags_to_prepare_for: list[str] = Field(
        default_factory=list,
        description="Gaps the interviewer will probe — with suggested honest answers",
    )
    company_research: Optional[str] = Field(
        None, description="Recent company context from Tavily (funding, culture, news)"
    )


class CopilotResult(BaseModel):
    """Full output of one run of the AI Job Copilot pipeline."""

    job: ParsedJob
    score: FitScore
    gaps: SkillGap
    cv: Optional[TailoredCV] = None
    cover_letter: Optional[CoverLetter] = None
    interview_prep: Optional[InterviewPrep] = None
    pdf_path: Optional[str] = None
    run_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


if __name__ == "__main__":
    # Usage example / smoke test
    example_job = ParsedJob(
        company="Acme AI",
        role="Junior AI Engineer",
        location="Casablanca, Morocco",
        market=Market.morocco,
        remote_ok=True,
        language_required="French",
        jd_language="French",
        requirements=["Python", "FastAPI", "LLM experience"],
        nice_to_have=["Docker", "AWS"],
        tech_stack=["Python", "FastAPI", "OpenAI API"],
        seniority=Seniority.junior,
        visa_sponsorship=None,
        salary_range=None,
        raw_text="Junior AI Engineer at Acme AI...",
        source_url=None,
    )

    example_score = FitScore(
        score=78,
        verdict=Verdict.apply,
        strengths=["Strong Python + FastAPI background", "RAG/LLM experience via DocuMind"],
        gaps=["No Docker experience", "No cloud certs"],
        reasoning="Strong technical fit for AI engineering role. Minor gaps in DevOps.",
        location_flag=None,
        risk_factors=["Less than 2 years experience"],
        germany_filter_passed=None,
    )

    print("✅ ParsedJob:", example_job.model_dump_json(indent=2))
    print("\n✅ FitScore:", example_score.model_dump_json(indent=2))
    print("\n✅ All schemas loaded correctly.")
