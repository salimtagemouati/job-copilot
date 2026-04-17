"""
PDF export module — MODULE 5b (cv_generator).

Renders TailoredCV as HTML via Jinja2, converts to PDF with pdfkit.
Falls back gracefully to saving HTML if wkhtmltopdf is not installed.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import shutil
from datetime import datetime
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from models.schemas import ParsedJob, TailoredCV
from config import settings
from utils.logger import get_logger

logger = get_logger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=True,
)

# wkhtmltopdf availability check (cached)
_WKHTMLTOPDF_AVAILABLE: bool | None = None


def _check_wkhtmltopdf() -> bool:
    """Check if wkhtmltopdf is installed and accessible."""
    global _WKHTMLTOPDF_AVAILABLE
    if _WKHTMLTOPDF_AVAILABLE is None:
        _WKHTMLTOPDF_AVAILABLE = shutil.which("wkhtmltopdf") is not None
        if not _WKHTMLTOPDF_AVAILABLE:
            logger.warning(
                "[pdf_export] wkhtmltopdf not found. Will save HTML fallback. "
                "Install with: sudo apt-get install wkhtmltopdf (Linux) or brew install wkhtmltopdf (macOS)"
            )
    return _WKHTMLTOPDF_AVAILABLE


def _make_filename(job: ParsedJob, ext: str) -> str:
    """
    Generates a clean filename: Company_Role_YYYY-MM-DD.ext

    Args:
        job: ParsedJob for naming
        ext: File extension (pdf or html)

    Returns:
        Sanitized filename string
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    company = "".join(c if c.isalnum() else "_" for c in job.company)[:20]
    role = "".join(c if c.isalnum() else "_" for c in job.role)[:20]
    return f"{company}_{role}_{date_str}.{ext}"


def render_cv_html(cv: TailoredCV, job: ParsedJob) -> str:
    """
    Renders the CV as an HTML string using Jinja2 template.

    Args:
        cv: TailoredCV data
        job: ParsedJob for context (company name, role, market)

    Returns:
        Rendered HTML string
    """
    template = _jinja_env.get_template("cv_template.html")
    html = template.render(cv=cv, job=job)
    return html


def export_pdf(cv: TailoredCV, job: ParsedJob) -> str:
    """
    Renders CV as HTML and converts to PDF with pdfkit.
    Falls back to saving HTML if wkhtmltopdf is not available.

    Args:
        cv: TailoredCV to render
        job: ParsedJob for filename and context

    Returns:
        Absolute path to the saved PDF (or HTML fallback)

    Example:
        >>> pdf_path = export_pdf(cv, job)
        >>> print(f"CV saved: {pdf_path}")
    """
    output_dir = Path(settings.pdf_output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    html_content = render_cv_html(cv, job)
    logger.info(f"[pdf_export] Rendered HTML ({len(html_content)} chars)")

    if _check_wkhtmltopdf():
        try:
            import pdfkit  # type: ignore

            filename = _make_filename(job, "pdf")
            output_path = output_dir / filename

            options = {
                "page-size": "A4",
                "margin-top": "10mm",
                "margin-bottom": "10mm",
                "margin-left": "12mm",
                "margin-right": "12mm",
                "encoding": "UTF-8",
                "quiet": "",
                "enable-local-file-access": "",
            }

            pdfkit.from_string(html_content, str(output_path), options=options)
            size_kb = output_path.stat().st_size // 1024
            logger.info(f"[pdf_export] PDF saved: {output_path} ({size_kb} KB)")
            return str(output_path)

        except Exception as e:
            logger.error(f"[pdf_export] pdfkit failed: {e}. Falling back to HTML.")

    # HTML fallback
    filename = _make_filename(job, "html")
    output_path = output_dir / filename
    output_path.write_text(html_content, encoding="utf-8")
    size_kb = output_path.stat().st_size // 1024
    logger.info(f"[pdf_export] HTML fallback saved: {output_path} ({size_kb} KB)")
    return str(output_path)


if __name__ == "__main__":
    from models.schemas import Market, Seniority

    # Build a minimal test CV
    test_cv = TailoredCV(
        summary=(
            "AI Engineer with strong Python and FastAPI background, "
            "specialized in RAG pipelines and LLM integration. "
            "Built DocuMind, a production-grade multi-tenant RAG SaaS."
        ),
        experience=[
            {
                "title": "Backend Engineering Intern",
                "company": "Royal Air Maroc",
                "duration": "June – August 2023",
                "bullets": [
                    "Built Spring Boot ERP module for operational cost management.",
                    "Delivered seamless interface for payment terms optimization.",
                ],
            }
        ],
        projects=[
            {
                "name": "DocuMind",
                "stack": ["FastAPI", "React 18", "Google Gemini", "FAISS", "Supabase", "Stripe"],
                "description": "Production RAG SaaS platform with multi-tenant support and subscription billing.",
                "highlights": ["Deployed on Render + Vercel", "Full Stripe integration"],
            },
            {
                "name": "BarberBook",
                "stack": ["React Native", "FastAPI", "Python"],
                "description": "Mobile barbershop booking platform for the Moroccan market.",
                "highlights": ["Real-time slot management"],
            },
        ],
        skills=["Python", "FastAPI", "React", "TypeScript", "LLMs", "RAG", "FAISS", "Supabase"],
        education=[
            {
                "degree": "BSc Computer Science — AI & Data Science",
                "institution": "Al Akhawayn University (AUI)",
                "year": "2024",
                "notes": "Exchange: University of Pisa, University of Zurich, Monroe College NY",
            }
        ],
        ats_keywords=["RAG", "LLM", "FastAPI", "Python", "MISSING: MLflow"],
    )

    test_job = ParsedJob(
        company="TestCo",
        role="Junior AI Engineer",
        location="Remote",
        market=Market.remote,
        remote_ok=True,
        language_required="English",
        jd_language="English",
        requirements=["Python", "LLM"],
        nice_to_have=[],
        tech_stack=["Python", "FastAPI"],
        seniority=Seniority.junior,
        raw_text="Junior AI Engineer at TestCo.",
    )

    print("Exporting CV...")
    path = export_pdf(test_cv, test_job)
    print(f"✅ Saved to: {path}")
