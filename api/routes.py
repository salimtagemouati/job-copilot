"""
FastAPI routes — Phase 3 API layer.

Wraps the entire pipeline as HTTP endpoints.
Useful for building a web UI or integrating with other tools later.

Start server: uvicorn api.routes:app --reload --port 8000
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from models.schemas import (
    Market, ParsedJob, FitScore, SkillGap,
    TailoredCV, CoverLetter, InterviewPrep, CopilotResult, Verdict,
)
from tracker.db import init_db, list_applications, update_status, get_stats, export_csv
from utils.logger import get_logger

logger = get_logger(__name__)

app = FastAPI(
    title="AI Job Copilot API",
    description="Salim's personal AI career assistant — REST API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response models ──────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    raw_text: str
    market: str = "morocco"
    source_url: Optional[str] = None
    generate_docs: bool = True  # False = score + gaps only


class AnalyzeResponse(BaseModel):
    job: ParsedJob
    score: FitScore
    gaps: SkillGap
    cv: Optional[TailoredCV] = None
    cover_letter: Optional[CoverLetter] = None
    interview_prep: Optional[InterviewPrep] = None
    pdf_path: Optional[str] = None
    market_filter_passed: bool = True
    market_filter_reason: str = ""


class StatusUpdateRequest(BaseModel):
    status: str
    notes: str = ""


# ── Startup ────────────────────────────────────────────────────────────────────

@app.on_event("startup")
def on_startup():
    init_db()
    logger.info("[api] FastAPI started. DB initialized.")


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["system"])
def health():
    """Health check — confirms API is running."""
    return {"status": "ok", "service": "AI Job Copilot"}


# ── Pipeline ───────────────────────────────────────────────────────────────────

@app.post("/analyze", response_model=AnalyzeResponse, tags=["pipeline"])
def analyze(req: AnalyzeRequest):
    """
    Run the full copilot pipeline on a job description.

    - Parses the JD
    - Applies market filter (Germany/Canada strict rules)
    - Scores fit
    - Analyzes skill gaps (always)
    - Generates CV, cover letter, interview prep (if Apply or Maybe)

    Does NOT auto-track. Use POST /tracker to save the result.
    """
    try:
        market = Market(req.market.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid market: {req.market}")

    if not req.raw_text.strip():
        raise HTTPException(status_code=400, detail="raw_text cannot be empty")

    # Parse
    try:
        from ingestion.parser import parse_job
        job = parse_job(req.raw_text, source_url=req.source_url)
        job.market = market
    except Exception as e:
        logger.error(f"[api/analyze] Parse failed: {e}")
        raise HTTPException(status_code=500, detail=f"Job parsing failed: {e}")

    # Market filter
    filter_passed = True
    filter_reason = "Passed (no filter for this market)"
    if market in (Market.germany, Market.canada):
        from scoring.market_filter import run_market_filter
        filter_passed, filter_reason = run_market_filter(job)
        if not filter_passed:
            raise HTTPException(
                status_code=422,
                detail=f"Market filter rejected: {filter_reason}",
            )

    # Score
    try:
        from scoring.engine import score_fit
        score = score_fit(job)
    except Exception as e:
        logger.error(f"[api/analyze] Scoring failed: {e}")
        raise HTTPException(status_code=500, detail=f"Scoring failed: {e}")

    # Gaps (always)
    try:
        from skill_gap.analyzer import analyze_gaps
        gaps = analyze_gaps(job, score)
    except Exception as e:
        logger.error(f"[api/analyze] Gap analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Gap analysis failed: {e}")

    # Documents
    cv = cover = prep = None
    pdf_path = ""

    if req.generate_docs and score.verdict in (Verdict.apply.value, Verdict.maybe.value):
        try:
            from cv_generator.tailor import tailor_cv
            from cover_letter.generator import generate_cover_letter
            from interview_prep.generator import generate_interview_prep
            from cv_generator.pdf_export import export_pdf

            cv = tailor_cv(job)
            cover = generate_cover_letter(job, cv, score)
            prep = generate_interview_prep(job, score)
            pdf_path = export_pdf(cv, job)
        except Exception as e:
            logger.error(f"[api/analyze] Document generation failed: {e}")
            # Don't raise — return what we have

    return AnalyzeResponse(
        job=job,
        score=score,
        gaps=gaps,
        cv=cv,
        cover_letter=cover,
        interview_prep=prep,
        pdf_path=pdf_path,
        market_filter_passed=filter_passed,
        market_filter_reason=filter_reason,
    )


# ── Tracker API ────────────────────────────────────────────────────────────────

@app.get("/tracker", tags=["tracker"])
def get_applications(
    market: Optional[str] = None,
    status: Optional[str] = None,
    min_score: Optional[int] = None,
    limit: int = 50,
):
    """List tracked applications with optional filters."""
    apps = list_applications(market=market, status=status, min_score=min_score, limit=limit)
    return {"count": len(apps), "applications": [a.model_dump() for a in apps]}


@app.patch("/tracker/{app_id}", tags=["tracker"])
def patch_application(app_id: int, req: StatusUpdateRequest):
    """Update an application's status."""
    app = update_status(app_id, req.status, notes=req.notes)
    if not app:
        raise HTTPException(status_code=404, detail=f"Application {app_id} not found")
    return app.model_dump()


@app.get("/tracker/stats", tags=["tracker"])
def get_tracker_stats():
    """Return aggregate statistics across all tracked applications."""
    return get_stats()


@app.get("/tracker/export/csv", tags=["tracker"])
def export_tracker_csv(market: Optional[str] = None, status: Optional[str] = None):
    """Export applications as CSV text."""
    from fastapi.responses import Response
    csv_data = export_csv(market=market, status=status)
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=applications.csv"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.routes:app", host="0.0.0.0", port=8000, reload=True)
