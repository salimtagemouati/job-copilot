"""
AI Job Copilot — CLI entry point.

Usage:
  python main.py analyze          # Paste a JD, run the full pipeline
  python main.py search           # Search for jobs by market
  python main.py tracker list     # Show tracked applications
  python main.py tracker update   # Update application status
  python main.py tracker stats    # Show aggregate stats
  python main.py tracker export   # Export to CSV
"""

import sys
import os

# Ensure project root is on path regardless of how the script is invoked
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pathlib import Path
from typing import Optional
from datetime import datetime

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box
from rich.prompt import Prompt, Confirm
from rich.rule import Rule

from models.schemas import Market, Verdict, ApplicationStatus
from config import settings
from tracker.db import init_db

# ── App setup ─────────────────────────────────────────────────────────────────
app = typer.Typer(
    name="job-copilot",
    help="🤖 AI Job Copilot — Apply smart, not often.",
    add_completion=False,
)
tracker_app = typer.Typer(help="Application tracker commands")
app.add_typer(tracker_app, name="tracker")

console = Console()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _market_from_str(s: str) -> Market:
    """Converts string to Market enum, with friendly error."""
    try:
        return Market(s.lower())
    except ValueError:
        console.print(f"[red]Unknown market '{s}'. Use: morocco, germany, canada, remote, other[/red]")
        raise typer.Exit(1)


def _verdict_color(verdict: str) -> str:
    return {"Apply": "green", "Maybe": "yellow", "Skip": "red"}.get(verdict, "white")


def _status_color(status: str) -> str:
    return {
        "Applied": "cyan", "Interview": "green", "Offer": "bold green",
        "Rejected": "red", "Ghosted": "dim",
    }.get(status, "white")


def _score_bar(score: int, width: int = 20) -> str:
    """Returns a visual score bar string."""
    filled = int((score / 100) * width)
    color = "green" if score >= 70 else "yellow" if score >= 45 else "red"
    bar = "█" * filled + "░" * (width - filled)
    return f"[{color}]{bar}[/{color}] {score}/100"


def _print_score_panel(score, job) -> None:
    """Renders a rich panel showing the fit score result."""
    verdict_color = _verdict_color(score.verdict)
    bar = _score_bar(score.score)

    content = Text()
    content.append(f"  Verdict: ", style="bold")
    content.append(f"{score.verdict}\n", style=f"bold {verdict_color}")
    content.append(f"  Score:   {bar}\n\n")

    content.append("  Strengths:\n", style="bold green")
    for s in score.strengths:
        content.append(f"    ✓ {s}\n", style="green")

    content.append("\n  Gaps:\n", style="bold red")
    for g in score.gaps:
        content.append(f"    ✗ {g}\n", style="red")

    content.append(f"\n  Reasoning: {score.reasoning}\n", style="dim")

    if score.risk_factors:
        content.append("\n  Risk factors:\n", style="bold yellow")
        for r in score.risk_factors:
            content.append(f"    ⚠ {r}\n", style="yellow")

    console.print(Panel(
        content,
        title=f"[bold]Fit Score — {job.company} | {job.role}[/bold]",
        border_style=verdict_color,
    ))


def _print_gaps_panel(gaps) -> None:
    """Renders the skill gap analysis panel."""
    content = Text()

    if gaps.missing_skills:
        content.append("  Missing skills:\n", style="bold")
        for skill in gaps.missing_skills:
            content.append(f"    • {skill}\n")

        content.append("\n  Learning priority (highest ROI first):\n", style="bold cyan")
        for i, skill in enumerate(gaps.learning_priority, 1):
            content.append(f"    {i}. {skill}\n", style="cyan")

        content.append("\n  Specific resources:\n", style="bold")
        for r in gaps.resources:
            content.append(f"    → {r}\n", style="dim")

        content.append(f"\n  Estimated effort: {gaps.estimated_effort}\n", style="bold")
        content.append(f"  Score impact: {gaps.score_impact}\n", style="bold green")
    else:
        content.append("  No critical gaps identified! Strong match.\n", style="green")

    console.print(Panel(content, title="[bold]Skill Gap Analysis[/bold]", border_style="blue"))


def _print_cover_letter(letter) -> None:
    """Renders the cover letter."""
    content = Text()
    content.append(f"Subject: {letter.subject_line}\n\n", style="bold")
    content.append(letter.body)
    content.append(f"\n\n[Word count: {letter.word_count}]", style="dim")
    console.print(Panel(content, title="[bold]Cover Letter[/bold]", border_style="green"))


def _print_interview_prep(prep) -> None:
    """Renders interview prep as a panel."""
    content = Text()

    if prep.likely_technical:
        content.append("  Technical Questions:\n", style="bold cyan")
        for q in prep.likely_technical:
            content.append(f"    Q: {q}\n", style="cyan")
            if q in prep.sample_answers:
                content.append(f"    A: {prep.sample_answers[q][:200]}...\n\n", style="dim")

    if prep.ml_ai_specific:
        content.append("\n  ML/AI Conceptual:\n", style="bold magenta")
        for q in prep.ml_ai_specific:
            content.append(f"    Q: {q}\n", style="magenta")

    if prep.likely_behavioral:
        content.append("\n  Behavioral:\n", style="bold yellow")
        for q in prep.likely_behavioral:
            content.append(f"    Q: {q}\n", style="yellow")

    if prep.red_flags_to_prepare_for:
        content.append("\n  ⚠  Red Flags to Address:\n", style="bold red")
        for rf in prep.red_flags_to_prepare_for:
            content.append(f"    • {rf}\n", style="red")

    if prep.company_research:
        content.append("\n  Company Research:\n", style="bold")
        content.append(f"    {prep.company_research[:400]}\n", style="dim")

    console.print(Panel(content, title="[bold]Interview Prep[/bold]", border_style="magenta"))


# ── ANALYZE COMMAND ────────────────────────────────────────────────────────────

@app.command()
def analyze(
    market: str = typer.Option(
        "morocco",
        "--market", "-m",
        help="Target market: morocco, germany, canada, remote, other",
    ),
    url: Optional[str] = typer.Option(
        None,
        "--url", "-u",
        help="Job posting URL (Tavily will fetch it)",
    ),
    file: Optional[Path] = typer.Option(
        None,
        "--file", "-f",
        help="Path to a .txt file containing the job description",
    ),
    no_docs: bool = typer.Option(
        False,
        "--no-docs",
        help="Skip document generation (score + gaps only)",
    ),
    yes: bool = typer.Option(
        False,
        "--yes", "-y",
        help="Auto-confirm tracking without prompt",
    ),
):
    """
    Analyze a job description — parse, score, generate CV + cover letter + interview prep.

    Paste the JD when prompted, or provide --url / --file.

    Examples:
      python main.py analyze --market morocco
      python main.py analyze --market germany --url https://jobs.zalando.com/123
      python main.py analyze --market remote --file ~/Downloads/jd.txt
    """
    init_db()
    mkt = _market_from_str(market)

    console.print(Rule(f"[bold]🤖 AI Job Copilot — {mkt.value.upper()} market[/bold]"))

    # ── Get raw JD text ───────────────────────────────────────────────────────
    raw_text: str = ""

    if url:
        console.print(f"[cyan]Fetching JD from URL: {url}[/cyan]")
        try:
            from ingestion.tavily_search import fetch_job_from_url
            fetched = fetch_job_from_url(url)
            if fetched:
                raw_text = fetched
                console.print(f"[green]✓ Fetched {len(raw_text)} chars[/green]")
            else:
                console.print("[yellow]⚠  URL fetch returned nothing. Falling back to paste.[/yellow]")
        except Exception as e:
            console.print(f"[yellow]⚠  URL fetch failed: {e}. Falling back to paste.[/yellow]")

    if file and not raw_text:
        if not file.exists():
            console.print(f"[red]File not found: {file}[/red]")
            raise typer.Exit(1)
        raw_text = file.read_text(encoding="utf-8")
        console.print(f"[green]✓ Loaded {len(raw_text)} chars from {file}[/green]")

    if not raw_text:
        console.print("\n[bold]Paste the job description below.[/bold]")
        console.print("[dim]Press Enter twice (blank line) when done:[/dim]\n")
        lines = []
        while True:
            try:
                line = input()
                if line == "" and lines and lines[-1] == "":
                    break
                lines.append(line)
            except EOFError:
                break
        raw_text = "\n".join(lines).strip()

    if not raw_text:
        console.print("[red]No job description provided. Exiting.[/red]")
        raise typer.Exit(1)

    # ── Duplicate check ───────────────────────────────────────────────────────
    from tracker.db import check_duplicate
    existing = check_duplicate(raw_text)
    if existing:
        console.print(
            f"\n[yellow]⚠  This JD was already tracked on "
            f"{existing.applied_date.strftime('%Y-%m-%d')} "
            f"(id={existing.id}, status={existing.status}).[/yellow]"
        )
        if not Confirm.ask("Continue anyway? (will not re-track)"):
            raise typer.Exit(0)

    # ── Step 1: Parse ─────────────────────────────────────────────────────────
    console.print("\n[bold cyan]Step 1/5 — Parsing job description...[/bold cyan]")
    try:
        from ingestion.parser import parse_job
        job = parse_job(raw_text, source_url=url)
        job.market = mkt  # override with user-provided market
        console.print(f"[green]✓ {job.company} | {job.role} | {job.location}[/green]")
    except Exception as e:
        console.print(f"[red]✗ Parsing failed: {e}[/red]")
        raise typer.Exit(1)

    # ── Step 2: Market pre-filter ─────────────────────────────────────────────
    if mkt == Market.germany or mkt == Market.canada:
        console.print(f"\n[bold cyan]Step 2/5 — Market filter ({mkt.value})...[/bold cyan]")
        from scoring.market_filter import run_market_filter
        eligible, reason = run_market_filter(job)
        if not eligible:
            console.print(Panel(
                f"[red]{reason}[/red]",
                title="[bold red]❌ Market Filter: REJECTED[/bold red]",
                border_style="red",
            ))
            raise typer.Exit(0)
        console.print(f"[green]✓ Market filter passed: {reason}[/green]")
    else:
        console.print(f"\n[dim]Step 2/5 — Market filter: {mkt.value} passes automatically[/dim]")

    # ── Step 3: Score ─────────────────────────────────────────────────────────
    console.print(f"\n[bold cyan]Step 3/5 — Scoring fit...[/bold cyan]")
    try:
        from scoring.engine import score_fit
        score = score_fit(job)
        _print_score_panel(score, job)
    except Exception as e:
        console.print(f"[red]✗ Scoring failed: {e}[/red]")
        raise typer.Exit(1)

    # ── Step 4: Gap analysis (always runs) ───────────────────────────────────
    console.print(f"\n[bold cyan]Step 4/5 — Analyzing skill gaps...[/bold cyan]")
    try:
        from skill_gap.analyzer import analyze_gaps
        gaps = analyze_gaps(job, score)
        _print_gaps_panel(gaps)
    except Exception as e:
        console.print(f"[yellow]⚠  Gap analysis failed: {e}[/yellow]")
        gaps = None

    # ── Step 5: Generate documents ────────────────────────────────────────────
    cv = cover = prep = None
    pdf_path = ""

    if score.verdict in (Verdict.apply.value, Verdict.maybe.value) and not no_docs:
        console.print(f"\n[bold cyan]Step 5/5 — Generating documents ({score.verdict})...[/bold cyan]")

        try:
            console.print("  [dim]Tailoring CV...[/dim]")
            from cv_generator.tailor import tailor_cv
            cv = tailor_cv(job)

            missing_skills = [k for k in cv.ats_keywords if k.lower().startswith("missing:")]
            if missing_skills:
                console.print(f"  [yellow]⚠  Skills flagged as missing from profile: {missing_skills}[/yellow]")

            console.print("  [dim]Generating cover letter...[/dim]")
            from cover_letter.generator import generate_cover_letter
            cover = generate_cover_letter(job, cv, score)
            _print_cover_letter(cover)

            console.print("  [dim]Generating interview prep...[/dim]")
            from interview_prep.generator import generate_interview_prep
            prep = generate_interview_prep(job, score)
            _print_interview_prep(prep)

            console.print("  [dim]Exporting CV to PDF/HTML...[/dim]")
            from cv_generator.pdf_export import export_pdf
            pdf_path = export_pdf(cv, job)
            console.print(f"  [green]✓ CV saved: {pdf_path}[/green]")

        except Exception as e:
            console.print(f"[yellow]⚠  Document generation partially failed: {e}[/yellow]")

    elif score.verdict == Verdict.skip.value:
        console.print(
            f"\n[dim]Step 5/5 — Skipping document generation (verdict: {score.verdict})[/dim]"
        )
    elif no_docs:
        console.print(f"\n[dim]Step 5/5 — Document generation skipped (--no-docs)[/dim]")

    # ── Track ─────────────────────────────────────────────────────────────────
    if score.verdict in (Verdict.apply.value, Verdict.maybe.value) and not existing:
        should_track = yes or Confirm.ask(
            f"\n[bold]Track this application in the database?[/bold]",
            default=True,
        )
        if should_track:
            from tracker.db import track_application
            app_record = track_application(job, score, pdf_path=pdf_path)
            if app_record:
                console.print(f"[green]✓ Tracked as id={app_record.id}[/green]")

    # ── Summary ───────────────────────────────────────────────────────────────
    console.print(Rule())
    verdict_color = _verdict_color(score.verdict)
    console.print(
        f"\n[bold]Summary:[/bold] {job.company} | {job.role} | "
        f"[{verdict_color}]{score.verdict}[/{verdict_color}] ({score.score}/100)"
    )
    if pdf_path:
        console.print(f"[dim]CV: {pdf_path}[/dim]")
    console.print()


# ── SEARCH COMMAND ─────────────────────────────────────────────────────────────

@app.command()
def search(
    market: str = typer.Option(
        "morocco",
        "--market", "-m",
        help="Market to search: morocco, germany, canada, remote",
    ),
    query: str = typer.Option(
        "",
        "--query", "-q",
        help="Custom search query (uses market defaults if empty)",
    ),
    limit: int = typer.Option(3, "--limit", "-n", help="Max results to fetch"),
    auto_analyze: bool = typer.Option(
        False,
        "--analyze",
        help="Automatically run the full pipeline on each result",
    ),
):
    """
    Search for jobs using Tavily and optionally run the pipeline on results.

    Examples:
      python main.py search --market morocco
      python main.py search --market germany --query "Junior ML Engineer Berlin English"
      python main.py search --market remote --analyze
    """
    init_db()
    mkt = _market_from_str(market)

    console.print(Rule(f"[bold]🔍 Job Search — {mkt.value.upper()}[/bold]"))
    console.print(f"[cyan]Searching Tavily for {mkt.value} opportunities...[/cyan]\n")

    try:
        from ingestion.tavily_search import search_jobs
        results = search_jobs(query=query, market=mkt, max_results=limit)
    except Exception as e:
        console.print(f"[red]Search failed: {e}[/red]")
        raise typer.Exit(1)

    if not results:
        console.print("[yellow]No results found. Try a different query or market.[/yellow]")
        raise typer.Exit(0)

    console.print(f"[green]✓ Found {len(results)} job listings[/green]\n")

    for i, raw_text in enumerate(results, 1):
        console.print(Rule(f"Result {i}/{len(results)}"))
        preview = raw_text[:300].replace("\n", " ")
        console.print(f"[dim]{preview}...[/dim]\n")

        if auto_analyze:
            if Confirm.ask(f"Run full analysis on result {i}?", default=True):
                try:
                    from ingestion.parser import parse_job
                    from scoring.market_filter import run_market_filter
                    from scoring.engine import score_fit
                    from skill_gap.analyzer import analyze_gaps

                    job = parse_job(raw_text)
                    job.market = mkt

                    if mkt in (Market.germany, Market.canada):
                        eligible, reason = run_market_filter(job)
                        if not eligible:
                            console.print(f"[red]Filtered: {reason}[/red]")
                            continue

                    score = score_fit(job)
                    gaps = analyze_gaps(job, score)

                    _print_score_panel(score, job)
                    _print_gaps_panel(gaps)

                except Exception as e:
                    console.print(f"[red]Analysis failed: {e}[/red]")


# ── TRACKER COMMANDS ───────────────────────────────────────────────────────────

@tracker_app.command("list")
def tracker_list(
    market: Optional[str] = typer.Option(None, "--market", "-m", help="Filter by market"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status"),
    min_score: Optional[int] = typer.Option(None, "--min-score", help="Minimum score"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max rows to show"),
):
    """
    List tracked applications with optional filters.

    Examples:
      python main.py tracker list
      python main.py tracker list --market germany --status Interview
      python main.py tracker list --min-score 70
    """
    init_db()
    from tracker.db import list_applications

    apps = list_applications(market=market, status=status, min_score=min_score, limit=limit)

    if not apps:
        console.print("[yellow]No applications found matching the filters.[/yellow]")
        return

    table = Table(
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        title=f"Applications ({len(apps)} shown)",
    )

    table.add_column("ID", style="dim", width=4)
    table.add_column("Company", min_width=14)
    table.add_column("Role", min_width=18)
    table.add_column("Market", width=8)
    table.add_column("Score", width=8)
    table.add_column("Verdict", width=8)
    table.add_column("Status", width=10)
    table.add_column("Date", width=10)

    for a in apps:
        verdict_color = _verdict_color(a.verdict)
        status_color = _status_color(a.status)
        score_color = "green" if a.score >= 70 else "yellow" if a.score >= 45 else "red"

        table.add_row(
            str(a.id),
            a.company,
            a.role[:30],
            a.market,
            f"[{score_color}]{a.score}[/{score_color}]",
            f"[{verdict_color}]{a.verdict}[/{verdict_color}]",
            f"[{status_color}]{a.status}[/{status_color}]",
            a.applied_date.strftime("%Y-%m-%d"),
        )

    console.print(table)


@tracker_app.command("update")
def tracker_update(
    app_id: int = typer.Argument(..., help="Application ID to update"),
    status: str = typer.Option(
        ...,
        "--status", "-s",
        help="New status: Applied, Interview, Offer, Rejected, Ghosted",
    ),
    notes: str = typer.Option("", "--notes", "-n", help="Notes to append"),
):
    """
    Update the status of an application.

    Examples:
      python main.py tracker update 3 --status Interview --notes "Phone screen Mon 10am"
      python main.py tracker update 7 --status Rejected
    """
    init_db()
    from tracker.db import update_status

    app_record = update_status(app_id, status, notes=notes)
    if app_record:
        console.print(
            f"[green]✓ Updated id={app_id}: {app_record.company} → status=[bold]{status}[/bold][/green]"
        )
    else:
        console.print(f"[red]✗ Update failed. Check id={app_id} exists and status is valid.[/red]")


@tracker_app.command("stats")
def tracker_stats():
    """
    Show aggregate statistics across all tracked applications.

    Example:
      python main.py tracker stats
    """
    init_db()
    from tracker.db import get_stats

    stats = get_stats()

    if stats.get("total", 0) == 0:
        console.print("[yellow]No applications tracked yet. Run 'analyze' to get started.[/yellow]")
        return

    console.print(Rule("[bold]📊 Application Stats[/bold]"))
    console.print(f"\n  [bold]Total tracked:[/bold] {stats['total']}")
    console.print(f"  [bold]Average fit score:[/bold] {stats['avg_score']}/100")
    console.print(
        f"  [bold]Interview rate:[/bold] [{('green' if stats['interview_rate'] > 0.15 else 'yellow')}]"
        f"{stats['interview_rate']:.0%}[/]"
    )

    # By market
    if stats.get("by_market"):
        console.print("\n  [bold]By market:[/bold]")
        for m, count in stats["by_market"].items():
            console.print(f"    {m:<12} {count}")

    # By status
    if stats.get("by_status"):
        console.print("\n  [bold]By status:[/bold]")
        for s, count in stats["by_status"].items():
            color = _status_color(s)
            console.print(f"    [{color}]{s:<14}[/{color}] {count}")

    # Top companies
    if stats.get("top_companies"):
        console.print("\n  [bold]Top applications by score:[/bold]")
        for t in stats["top_companies"]:
            score_color = "green" if t["score"] >= 70 else "yellow"
            console.print(
                f"    [{score_color}]{t['score']:>3}[/{score_color}]  "
                f"{t['company']:<20} {t['role'][:30]}"
            )

    console.print()


@tracker_app.command("export")
def tracker_export(
    output: Path = typer.Option(
        Path("tracker_export.csv"),
        "--output", "-o",
        help="Output CSV file path",
    ),
    market: Optional[str] = typer.Option(None, "--market", "-m", help="Filter by market"),
    status: Optional[str] = typer.Option(None, "--status", "-s", help="Filter by status"),
):
    """
    Export applications to CSV.

    Examples:
      python main.py tracker export
      python main.py tracker export --output ~/Desktop/applications.csv
      python main.py tracker export --market germany --output de_apps.csv
    """
    init_db()
    from tracker.db import export_csv

    csv_data = export_csv(market=market, status=status)
    output.write_text(csv_data, encoding="utf-8")

    line_count = csv_data.count("\n") - 1  # subtract header
    console.print(f"[green]✓ Exported {line_count} applications to: {output}[/green]")


@tracker_app.command("delete")
def tracker_delete(
    app_id: int = typer.Argument(..., help="Application ID to delete"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """
    Delete an application from the tracker.

    Example:
      python main.py tracker delete 5
    """
    init_db()
    from tracker.db import get_application, delete_application

    app_record = get_application(app_id)
    if not app_record:
        console.print(f"[red]Application id={app_id} not found.[/red]")
        raise typer.Exit(1)

    console.print(f"Delete: [bold]{app_record.company} | {app_record.role}[/bold] (id={app_id})?")

    if not yes:
        if not Confirm.ask("[red]Confirm delete?[/red]", default=False):
            console.print("[dim]Cancelled.[/dim]")
            raise typer.Exit(0)

    if delete_application(app_id):
        console.print(f"[green]✓ Deleted id={app_id}[/green]")
    else:
        console.print(f"[red]✗ Delete failed.[/red]")


# ── ENTRY POINT ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app()
