"""
Application Tracker database layer — MODULE 8b (tracker).

Features:
- Auto-init SQLite DB on first run
- Duplicate detection via jd_hash (SHA256)
- CRUD: create, update status, list, filter, delete
- Export to CSV
- Stats: apply rate, interview rate by market
- All DB failures are logged — never crash the pipeline
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import csv
import io
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import SQLModel, Session, create_engine, select, func

from tracker.models import Application
from models.schemas import ParsedJob, FitScore, ApplicationStatus, Market
from utils.validators import hash_text
from utils.logger import get_logger
from config import settings

logger = get_logger(__name__)

# ── Engine (module-level singleton) ───────────────────────────────────────────
_engine = None


def get_engine():
    """Returns the shared SQLite engine, creating it if needed."""
    global _engine
    if _engine is None:
        db_url = f"sqlite:///{settings.db_path}"
        _engine = create_engine(db_url, echo=False)
        logger.info(f"[tracker] DB engine created: {db_url}")
    return _engine


def init_db() -> None:
    """
    Creates all tables if they don't exist.
    Safe to call multiple times — idempotent.

    Example:
        >>> init_db()
        # DB tables created (or already existed)
    """
    SQLModel.metadata.create_all(get_engine())
    logger.info("[tracker] DB initialized (tables created or already exist)")


# ── CREATE ─────────────────────────────────────────────────────────────────────

def track_application(
    job: ParsedJob,
    score: FitScore,
    pdf_path: str = "",
    notes: str = "",
) -> Optional[Application]:
    """
    Logs a job application to the tracker database.

    Skips silently if this JD hash already exists (duplicate detection).
    Should be called for Apply and Maybe verdicts only (caller's responsibility).

    Args:
        job: ParsedJob with all job metadata
        score: FitScore with score, verdict, etc.
        pdf_path: Path to generated CV PDF (empty string if not generated)
        notes: Optional free-text notes

    Returns:
        The created Application record, or None if duplicate / DB error

    Example:
        >>> app = track_application(job, score, pdf_path="outputs/pdfs/Zalando_JML_2025-04-14.pdf")
        >>> if app:
        ...     print(f"Tracked: {app.id} — {app.company}")
    """
    jd_hash = hash_text(job.raw_text)

    try:
        with Session(get_engine()) as session:
            # Duplicate check
            existing = session.exec(
                select(Application).where(Application.jd_hash == jd_hash)
            ).first()

            if existing:
                logger.warning(
                    f"[tracker] Duplicate JD detected for {job.company} | {job.role}. "
                    f"Already tracked as id={existing.id} (status={existing.status}). Skipping."
                )
                return None

            app = Application(
                company=job.company,
                role=job.role,
                market=job.market if isinstance(job.market, str) else job.market.value,
                location=job.location,
                source_url=job.source_url or "",
                score=score.score,
                verdict=score.verdict if isinstance(score.verdict, str) else score.verdict.value,
                status=ApplicationStatus.applied.value,
                applied_date=datetime.now(timezone.utc),
                last_updated=datetime.now(timezone.utc),
                jd_hash=jd_hash,
                pdf_path=pdf_path,
                notes=notes,
            )

            session.add(app)
            session.commit()
            session.refresh(app)

            logger.info(
                f"[tracker] Tracked: id={app.id} | {app.company} | {app.role} | "
                f"score={app.score} | verdict={app.verdict} | market={app.market}"
            )
            return app

    except Exception as e:
        logger.error(f"[tracker] Failed to track application for {job.company}: {e}")
        return None


# ── UPDATE ─────────────────────────────────────────────────────────────────────

def update_status(
    app_id: int,
    new_status: str,
    notes: str = "",
) -> Optional[Application]:
    """
    Updates the status of an existing application.

    Args:
        app_id: Primary key of the Application record
        new_status: New status string (Applied/Interview/Offer/Rejected/Ghosted)
        notes: Optional notes to append (appended, not replaced)

    Returns:
        Updated Application, or None if not found / DB error

    Example:
        >>> app = update_status(3, "Interview", "Phone screen scheduled for Monday")
    """
    # Validate status value
    valid_statuses = {s.value for s in ApplicationStatus}
    if new_status not in valid_statuses:
        logger.error(f"[tracker] Invalid status '{new_status}'. Must be one of: {valid_statuses}")
        return None

    try:
        with Session(get_engine()) as session:
            app = session.get(Application, app_id)
            if not app:
                logger.warning(f"[tracker] Application id={app_id} not found")
                return None

            old_status = app.status
            app.status = new_status
            app.last_updated = datetime.now(timezone.utc)
            if notes:
                separator = "\n" if app.notes else ""
                app.notes = app.notes + separator + f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d')}] {notes}"

            session.add(app)
            session.commit()
            session.refresh(app)

            logger.info(
                f"[tracker] Updated id={app_id} | {app.company} | "
                f"{old_status} → {new_status}"
            )
            return app

    except Exception as e:
        logger.error(f"[tracker] Failed to update status for id={app_id}: {e}")
        return None


# ── READ / QUERY ───────────────────────────────────────────────────────────────

def list_applications(
    market: Optional[str] = None,
    status: Optional[str] = None,
    min_score: Optional[int] = None,
    max_score: Optional[int] = None,
    limit: int = 50,
) -> list[Application]:
    """
    Lists applications with optional filtering.

    Args:
        market: Filter by market (morocco/germany/canada/remote/other)
        status: Filter by status (Applied/Interview/Offer/Rejected/Ghosted)
        min_score: Minimum fit score (inclusive)
        max_score: Maximum fit score (inclusive)
        limit: Max rows to return (default 50)

    Returns:
        List of matching Application records, newest first

    Example:
        >>> apps = list_applications(market="germany", status="Interview")
        >>> for a in apps:
        ...     print(f"{a.company} | {a.score} | {a.status}")
    """
    try:
        with Session(get_engine()) as session:
            query = select(Application)

            if market:
                query = query.where(Application.market == market)
            if status:
                query = query.where(Application.status == status)
            if min_score is not None:
                query = query.where(Application.score >= min_score)
            if max_score is not None:
                query = query.where(Application.score <= max_score)

            query = query.order_by(Application.applied_date.desc()).limit(limit)  # type: ignore
            results = session.exec(query).all()

            logger.info(f"[tracker] Query returned {len(results)} applications")
            return list(results)

    except Exception as e:
        logger.error(f"[tracker] List query failed: {e}")
        return []


def get_application(app_id: int) -> Optional[Application]:
    """
    Fetches a single application by ID.

    Args:
        app_id: Primary key

    Returns:
        Application or None if not found
    """
    try:
        with Session(get_engine()) as session:
            return session.get(Application, app_id)
    except Exception as e:
        logger.error(f"[tracker] get_application({app_id}) failed: {e}")
        return None


def check_duplicate(raw_text: str) -> Optional[Application]:
    """
    Checks if a JD has already been tracked (by SHA256 hash).

    Args:
        raw_text: Raw JD text to check

    Returns:
        Existing Application if found, else None

    Example:
        >>> dup = check_duplicate(raw_text)
        >>> if dup:
        ...     print(f"Already tracked as id={dup.id} (status={dup.status})")
    """
    jd_hash = hash_text(raw_text)
    try:
        with Session(get_engine()) as session:
            return session.exec(
                select(Application).where(Application.jd_hash == jd_hash)
            ).first()
    except Exception as e:
        logger.error(f"[tracker] Duplicate check failed: {e}")
        return None


# ── STATS ──────────────────────────────────────────────────────────────────────

def get_stats() -> dict:
    """
    Returns aggregate stats across all tracked applications.

    Returns dict with:
    - total: total applications
    - by_market: count per market
    - by_status: count per status
    - by_verdict: count per verdict
    - interview_rate: % of Applied that reached Interview+
    - avg_score: average fit score
    - top_companies: top 5 companies by score

    Example:
        >>> stats = get_stats()
        >>> print(f"Total: {stats['total']}, Interview rate: {stats['interview_rate']:.0%}")
    """
    try:
        with Session(get_engine()) as session:
            all_apps = session.exec(select(Application)).all()

            if not all_apps:
                return {"total": 0, "message": "No applications tracked yet"}

            total = len(all_apps)

            # By market
            by_market: dict[str, int] = {}
            by_status: dict[str, int] = {}
            by_verdict: dict[str, int] = {}
            scores = []

            for app in all_apps:
                by_market[app.market] = by_market.get(app.market, 0) + 1
                by_status[app.status] = by_status.get(app.status, 0) + 1
                by_verdict[app.verdict] = by_verdict.get(app.verdict, 0) + 1
                scores.append(app.score)

            applied_count = by_status.get("Applied", 0) + by_status.get("Interview", 0) + \
                           by_status.get("Offer", 0) + by_status.get("Rejected", 0) + \
                           by_status.get("Ghosted", 0)
            interview_plus = by_status.get("Interview", 0) + by_status.get("Offer", 0)
            interview_rate = interview_plus / applied_count if applied_count > 0 else 0.0

            avg_score = sum(scores) / len(scores) if scores else 0.0

            # Top 5 by score
            top = sorted(all_apps, key=lambda a: a.score, reverse=True)[:5]
            top_companies = [
                {"company": a.company, "role": a.role, "score": a.score, "status": a.status}
                for a in top
            ]

            return {
                "total": total,
                "by_market": by_market,
                "by_status": by_status,
                "by_verdict": by_verdict,
                "interview_rate": round(interview_rate, 4),
                "avg_score": round(avg_score, 1),
                "top_companies": top_companies,
            }

    except Exception as e:
        logger.error(f"[tracker] Stats failed: {e}")
        return {"error": str(e)}


# ── EXPORT ─────────────────────────────────────────────────────────────────────

def export_csv(
    market: Optional[str] = None,
    status: Optional[str] = None,
) -> str:
    """
    Exports filtered applications to CSV string.

    Args:
        market: Optional market filter
        status: Optional status filter

    Returns:
        CSV string (can be written to file or printed)

    Example:
        >>> csv_data = export_csv(market="germany")
        >>> Path("tracker_export.csv").write_text(csv_data)
    """
    apps = list_applications(market=market, status=status, limit=1000)

    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "id", "company", "role", "market", "location",
        "score", "verdict", "status",
        "applied_date", "last_updated",
        "source_url", "pdf_path", "notes",
    ])

    for app in apps:
        writer.writerow([
            app.id, app.company, app.role, app.market, app.location,
            app.score, app.verdict, app.status,
            app.applied_date.strftime("%Y-%m-%d %H:%M"),
            app.last_updated.strftime("%Y-%m-%d %H:%M"),
            app.source_url, app.pdf_path, app.notes,
        ])

    csv_str = output.getvalue()
    logger.info(f"[tracker] Exported {len(apps)} applications to CSV")
    return csv_str


# ── DELETE ─────────────────────────────────────────────────────────────────────

def delete_application(app_id: int) -> bool:
    """
    Deletes an application by ID. Use with caution.

    Args:
        app_id: Primary key to delete

    Returns:
        True if deleted, False if not found or error
    """
    try:
        with Session(get_engine()) as session:
            app = session.get(Application, app_id)
            if not app:
                logger.warning(f"[tracker] Delete: id={app_id} not found")
                return False
            session.delete(app)
            session.commit()
            logger.info(f"[tracker] Deleted application id={app_id}")
            return True
    except Exception as e:
        logger.error(f"[tracker] Delete failed for id={app_id}: {e}")
        return False


if __name__ == "__main__":
    from models.schemas import Market, Seniority, Verdict

    print("Initializing DB...")
    init_db()

    # Create a test job + score
    test_job = ParsedJob(
        company="TestCorp",
        role="Junior AI Engineer",
        location="Casablanca, Morocco",
        market=Market.morocco,
        remote_ok=True,
        language_required="French",
        jd_language="French",
        requirements=["Python", "FastAPI", "LLMs"],
        nice_to_have=["Docker"],
        tech_stack=["Python", "FastAPI"],
        seniority=Seniority.junior,
        raw_text="Junior AI Engineer at TestCorp Casablanca. Unique text " + str(datetime.now(timezone.utc)),
    )

    test_score = FitScore(
        score=75,
        verdict=Verdict.apply,
        strengths=["Python strong", "RAG experience"],
        gaps=["No Docker"],
        reasoning="Good fit.",
        risk_factors=["< 2 years experience"],
    )

    # Track it
    print("\nTracking application...")
    app = track_application(test_job, test_score, pdf_path="outputs/pdfs/test.pdf")
    if app:
        print(f"✅ Tracked: id={app.id} | {app.company} | score={app.score}")

        # Update status
        print("\nUpdating to Interview...")
        updated = update_status(app.id, "Interview", notes="Phone screen scheduled")
        if updated:
            print(f"✅ Status updated: {updated.status}")

        # Stats
        print("\nStats:")
        stats = get_stats()
        print(f"  Total: {stats.get('total')}")
        print(f"  By market: {stats.get('by_market')}")
        print(f"  Interview rate: {stats.get('interview_rate', 0):.0%}")

        # Export CSV
        print("\nExporting CSV...")
        csv_data = export_csv()
        print(csv_data[:300])

        # Duplicate detection
        print("\nTesting duplicate detection...")
        dup = track_application(test_job, test_score)
        if dup is None:
            print("✅ Duplicate correctly blocked")
    else:
        print("⚠️  Tracking returned None (may be a duplicate from previous run)")
