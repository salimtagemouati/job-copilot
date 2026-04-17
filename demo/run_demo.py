"""
Demo mode for AI Job Copilot.

Runs the full pipeline using pre-computed fixture data — no API calls, no keys needed.
Purpose: portfolio demos, CI testing, showing the project to interviewers.

Usage:
    python demo/run_demo.py
    python demo/run_demo.py --market germany
    python demo/run_demo.py --scenario senior   # shows Skip + gap analysis
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
from datetime import datetime, timezone

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.rule import Rule
from rich import box

from models.schemas import (
    ParsedJob, FitScore, SkillGap, TailoredCV, CoverLetter,
    InterviewPrep, CopilotResult,
    Market, Seniority, Verdict,
)

console = Console()

# ── Demo fixtures — represent realistic pipeline outputs ──────────────────────

DEMO_SCENARIOS = {
    "morocco": {
        "label": "Junior AI Engineer — Casablanca (Apply ✓)",
        "job": ParsedJob(
            company="Atlas Intelligence",
            role="Junior AI Engineer",
            location="Casablanca, Morocco",
            market=Market.morocco,
            remote_ok=True,
            language_required="French",
            jd_language="French",
            requirements=["Python 3.10+", "FastAPI", "LLM integration", "RAG pipelines", "0-2 years"],
            nice_to_have=["Docker", "React", "Supabase"],
            tech_stack=["Python", "FastAPI", "OpenAI API", "FAISS", "PostgreSQL"],
            seniority=Seniority.junior,
            visa_sponsorship=None,
            salary_range="8 000 – 12 000 MAD / mois",
            raw_text="Junior AI Engineer at Atlas Intelligence Casablanca. Python FastAPI LLM RAG.",
        ),
        "score": FitScore(
            score=81,
            verdict=Verdict.apply,
            strengths=[
                "DocuMind directly matches RAG pipeline requirement — production-grade evidence",
                "FastAPI + Python stack alignment is exact",
                "FAISS vector store experience from DocuMind maps to JD requirement",
                "Junior/0-2 YOE level matches exactly",
                "Morocco market — no visa or relocation complexity",
            ],
            gaps=[
                "Docker not in current stack (listed as nice-to-have, not hard requirement)",
                "No PostgreSQL production experience (SQLite used in projects)",
            ],
            reasoning=(
                "Strong fit. DocuMind is a production RAG SaaS that demonstrates every core "
                "requirement. Python + FastAPI + FAISS stack is identical. Minor gaps in Docker "
                "and PostgreSQL are listed as bonuses, not hard requirements."
            ),
            risk_factors=["< 2 years total experience", "No prior full-time employment at tech company"],
            location_flag=None,
            germany_filter_passed=None,
        ),
        "gaps": SkillGap(
            missing_skills=["Docker", "PostgreSQL production experience"],
            learning_priority=["Docker", "PostgreSQL"],
            resources=[
                "Docker: 'Docker for Beginners' — Play With Docker free labs (docker.com/play-with-docker), ~6h",
                "PostgreSQL: 'Learn PostgreSQL Tutorial' — free on freeCodeCamp YouTube, ~4h + hands-on",
            ],
            estimated_effort="1 week part-time — both are learnable quickly",
            score_impact="+5 points — would push score to ~86, still same Apply verdict",
        ),
        "cover_letter": CoverLetter(
            subject_line="Candidature — Ingénieur IA Junior | Atlas Intelligence",
            body=(
                "Atlas Intelligence recherche un Ingénieur IA Junior, et mon profil correspond "
                "directement à vos besoins techniques.\n\n"
                "J'ai conçu et déployé DocuMind, une plateforme SaaS RAG en production utilisant "
                "FastAPI, Google Gemini, FAISS et Supabase — avec support multi-tenant et "
                "facturation Stripe. Ce projet illustre exactement les compétences que vous "
                "recherchez : pipelines RAG, intégration LLM, et APIs REST robustes.\n\n"
                "Mon cursus en IA et Data Science à l'Université Al Akhawayn, complété par des "
                "semestres d'échange à Pise, Zurich et New York, m'a permis de développer une "
                "rigueur technique et une capacité d'adaptation que je suis prêt à mettre au "
                "service de vos clients enterprise.\n\n"
                "Je serais ravi d'échanger sur la façon dont mon expérience peut contribuer "
                "à vos projets d'IA. Mes formations à Pise, Zurich et New York m'ont appris à travailler "
                "rapidement dans des contextes nouveaux. Disponible pour un entretien à votre convenance."
            ),
            word_count=150,
        ),
        "interview_prep": InterviewPrep(
            likely_technical=[
                "Walk me through how you built the RAG pipeline in DocuMind — chunking strategy, embedding model, retrieval approach.",
                "How does FAISS work and what are its limitations compared to managed vector stores like Pinecone?",
                "You used multi-tenant architecture in DocuMind. How did you handle data isolation between tenants?",
                "Explain how you'd improve retrieval quality if users report irrelevant answers.",
                "How would you monitor and debug an LLM-based system in production?",
            ],
            likely_behavioral=[
                "Tell me about a time you had to make a technical decision with incomplete information.",
                "Describe how you managed the DocuMind project from idea to deployment — what was hardest?",
            ],
            ml_ai_specific=[
                "What's the difference between RAG and fine-tuning? When would you choose each?",
                "How do you evaluate the quality of a RAG system's outputs?",
                "What is hallucination in LLMs and how did you mitigate it in DocuMind?",
            ],
            sample_answers={
                "Walk me through how you built the RAG pipeline in DocuMind": (
                    "In DocuMind, documents are uploaded, split into overlapping chunks of ~500 tokens "
                    "with 50-token overlap to preserve context across boundaries. Each chunk is embedded "
                    "using Google Gemini's embedding model and stored in FAISS. At query time, the user's "
                    "question is embedded with the same model, FAISS returns top-k similar chunks via "
                    "cosine similarity, and those chunks are injected into a Gemini prompt as context. "
                    "I added a reranking step to filter low-relevance chunks before generation."
                ),
            },
            red_flags_to_prepare_for=[
                "Gap: Less than 2 years experience → Strategy: Emphasize DocuMind is live in production, "
                "not a toy project. Mention the full-stack nature: auth, billing, multi-tenancy, deployment.",
                "Gap: No full-time tech employment → Strategy: Frame the internship at Royal Air Maroc "
                "as real enterprise context (ERP systems, business-critical data), and freelance work as "
                "client-facing delivery experience.",
            ],
            company_research=(
                "Atlas Intelligence is a Casablanca-based AI consultancy focused on enterprise LLM "
                "applications for Moroccan and North African markets. They work primarily in French "
                "and Arabic. Recent projects include document automation for financial institutions."
            ),
        ),
    },

    "germany": {
        "label": "ML Engineer — Berlin, Personio (Maybe →)",
        "job": ParsedJob(
            company="Personio",
            role="Junior Machine Learning Engineer",
            location="Munich, Germany",
            market=Market.germany,
            remote_ok=True,
            language_required="English",
            jd_language="English",
            requirements=["Python", "ML frameworks (PyTorch/sklearn)", "FastAPI", "MLflow", "1-3 years"],
            nice_to_have=["Docker", "Kubernetes basics", "AWS basics"],
            tech_stack=["Python", "PyTorch", "scikit-learn", "FastAPI", "MLflow", "Docker"],
            seniority=Seniority.junior,
            visa_sponsorship=True,
            salary_range="€45,000 – €60,000 / year",
            raw_text="Junior ML Engineer at Personio Munich. English working language. Visa sponsorship.",
        ),
        "score": FitScore(
            score=58,
            verdict=Verdict.maybe,
            strengths=[
                "Python strong — core requirement met",
                "FastAPI for model serving matches directly",
                "LLM/ML experience through DocuMind and Forest Fire Prediction capstone",
                "English fluency — working language requirement met",
                "Visa sponsorship available — Germany filter passed",
            ],
            gaps=[
                "No PyTorch experience (used Gemini API, not raw framework training)",
                "No MLflow or experiment tracking experience",
                "No Docker production usage",
                "scikit-learn not in current stack",
            ],
            reasoning=(
                "Solid Python and FastAPI foundation, but gaps in raw ML framework experience "
                "(PyTorch, scikit-learn) and MLOps tooling (MLflow) reduce fit. "
                "Reachable with 2-3 weeks of focused prep — apply with honest framing."
            ),
            risk_factors=[
                "No PyTorch training experience — critical for ML role",
                "MLflow gap will likely surface in technical screen",
                "< 2 years experience for a role expecting 1-3 YOE",
            ],
            location_flag="Germany — English JD, visa sponsorship confirmed. Filter passed.",
            germany_filter_passed=True,
        ),
        "gaps": SkillGap(
            missing_skills=["PyTorch", "scikit-learn", "MLflow", "Docker"],
            learning_priority=["PyTorch", "MLflow", "scikit-learn", "Docker"],
            resources=[
                "PyTorch: 'Deep Learning with PyTorch: A 60 Minute Blitz' — official tutorial (pytorch.org), ~4h",
                "MLflow: MLflow Quickstart docs (mlflow.org) + Databricks free MLflow course on Coursera, ~6h",
                "scikit-learn: 'scikit-learn User Guide' — official docs, focus on pipelines chapter, ~4h",
                "Docker: 'Docker for Beginners' — Play With Docker labs (docker.com/play-with-docker), ~5h",
            ],
            estimated_effort="2-3 weeks part-time, prioritise PyTorch and MLflow",
            score_impact="+18 points — would move from 58 (Maybe) to ~76 (Apply)",
        ),
        "cover_letter": CoverLetter(
            subject_line="Application — Junior Machine Learning Engineer | Personio",
            body=(
                "I'm applying for the Junior Machine Learning Engineer role at Personio.\n\n"
                "My strongest relevant project is DocuMind — a production RAG SaaS I built "
                "end-to-end using FastAPI, Google Gemini, FAISS, and Supabase. It handles "
                "multi-tenant document Q&A with vector search and Stripe billing, deployed on "
                "Render and Vercel. This gave me hands-on experience designing ML-powered APIs "
                "at production scale — directly applicable to Personio's ML engineering work.\n\n"
                "My BSc in AI and Data Science from Al Akhawayn University, combined with my "
                "Forest Fire Prediction capstone (YOLOv8, GIS data), shows depth in applied ML. "
                "I'm actively building PyTorch and MLflow proficiency to close the gap between "
                "my current stack and your requirements — and I'm honest about where I am today.\n\n"
                "I'd welcome a technical conversation to show what I can do. Happy to do a "
                "take-home or live coding screen at your convenience."
            ),
            word_count=175,
        ),
        "interview_prep": InterviewPrep(
            likely_technical=[
                "Walk me through training a classifier with scikit-learn — preprocessing, pipeline, evaluation.",
                "What's the difference between a train/val/test split and cross-validation?",
                "How would you track and compare 20 ML experiments systematically?",
                "You built a model serving API with FastAPI — how would you add model versioning?",
                "What metrics would you use to evaluate a binary classifier on imbalanced data?",
            ],
            likely_behavioral=[
                "Tell me about a project where you had to learn something new quickly under pressure.",
                "Describe a time you received critical technical feedback and how you responded.",
            ],
            ml_ai_specific=[
                "Explain gradient descent and why learning rate matters.",
                "What is overfitting and what techniques did you use to prevent it?",
                "How does a transformer architecture differ from an LSTM for sequence tasks?",
            ],
            sample_answers={
                "Tell me about a project where you had to learn something new quickly": (
                    "During my Forest Fire Prediction capstone, I had to learn YOLOv8 object detection "
                    "and GIS data processing within 3 weeks to meet the deadline. I broke it down: "
                    "one week on YOLOv8 fundamentals using the official docs and a satellite imagery "
                    "dataset, one week on GIS data pipelines with Moroccan regional data, and one week "
                    "integrating both into the FastAPI serving layer. The model achieved 87% precision "
                    "on the validation set and was presented to university faculty."
                ),
            },
            red_flags_to_prepare_for=[
                "Gap: No PyTorch → Strategy: Acknowledge it directly. Say: 'I've been using Gemini's "
                "API rather than raw PyTorch, but I understand the underlying concepts — I'm actively "
                "working through the PyTorch 60-minute blitz and building a small classifier project.'",
                "Gap: No MLflow → Strategy: 'I tracked experiments manually with structured logs in "
                "DocuMind. MLflow is next on my list — I've already read through the quickstart.'",
            ],
            company_research=(
                "Personio is Germany's leading HR software platform, valued at ~$8.5B. "
                "They serve 10,000+ SMEs across Europe. Engineering culture emphasises "
                "Python, data-driven product decisions, and English-first collaboration. "
                "Recent ML initiatives focus on HR analytics, automation, and AI-assisted "
                "recruitment tools. Team is 30+ nationalities, remote-friendly."
            ),
        ),
    },

    "senior": {
        "label": "Senior ML Research Engineer — DeepMind (Skip ✗)",
        "job": ParsedJob(
            company="DeepMind",
            role="Senior ML Research Engineer",
            location="London, UK / Remote EU",
            market=Market.remote,
            remote_ok=True,
            language_required="English",
            jd_language="English",
            requirements=[
                "PhD preferred", "7+ years production ML", "PyTorch + JAX",
                "Published research (NeurIPS/ICML/ICLR)", "Kubernetes", "Google Cloud certs",
            ],
            nice_to_have=["RLHF experience", "distributed training at scale"],
            tech_stack=["Python", "PyTorch", "JAX", "Kubernetes", "Vertex AI"],
            seniority=Seniority.senior,
            visa_sponsorship=None,
            salary_range="£120,000 – £180,000 + equity",
            raw_text="Senior ML Research Engineer at DeepMind. PhD preferred. 7+ YOE required.",
        ),
        "score": FitScore(
            score=22,
            verdict=Verdict.skip,
            strengths=["Python — relevant foundation"],
            gaps=[
                "Requires 7+ years experience — Salim has < 2",
                "PhD preferred — not applicable",
                "No PyTorch or JAX research experience",
                "No published ML research",
                "No Kubernetes production experience",
                "No Google Cloud certifications",
                "No distributed training experience",
            ],
            reasoning=(
                "This role is 5-7 years beyond current level. Applying would be noise, "
                "not signal. Use this as a north-star: the gap analysis shows the exact "
                "roadmap to eventually target roles like this."
            ),
            risk_factors=["Significant experience and qualification gap on every dimension"],
            location_flag=None,
            germany_filter_passed=None,
        ),
        "gaps": SkillGap(
            missing_skills=["PyTorch", "JAX", "Research publication", "Kubernetes", "GCP certs", "Distributed training"],
            learning_priority=["PyTorch", "Kubernetes basics", "GCP fundamentals", "JAX"],
            resources=[
                "PyTorch: 'Deep Learning with PyTorch' book (free on pytorch.org) + fast.ai course",
                "Kubernetes: KodeKloud 'Kubernetes for Beginners' (free tier, ~12h)",
                "GCP: Google Cloud Skills Boost free trial — 'Machine Learning on GCP' path",
                "Research: Start reading papers on arXiv (cs.LG), implement 1 paper per month",
                "JAX: Google's JAX tutorials (jax.readthedocs.io) after PyTorch fundamentals",
            ],
            estimated_effort=(
                "18-24 months of deliberate practice to be competitive for mid-level ML roles. "
                "Senior research roles at DeepMind require 5-7+ more years realistically."
            ),
            score_impact=(
                "+40 points over 18 months → would qualify for mid-level ML roles (score ~62). "
                "Senior research roles require PhD-level work and publications — different track."
            ),
        ),
    },
}


def _verdict_color(v: str) -> str:
    return {"Apply": "green", "Maybe": "yellow", "Skip": "red"}.get(v, "white")


def _score_bar(score: int) -> str:
    w = 22
    filled = int((score / 100) * w)
    color = "green" if score >= 70 else "yellow" if score >= 45 else "red"
    return f"[{color}]{'█' * filled}{'░' * (w - filled)}[/{color}] {score}/100"


def run_demo(scenario_key: str = "morocco") -> None:
    s = DEMO_SCENARIOS.get(scenario_key)
    if not s:
        console.print(f"[red]Unknown scenario '{scenario_key}'. Choose: {list(DEMO_SCENARIOS)}")
        return

    job: ParsedJob         = s["job"]
    score: FitScore        = s["score"]
    gaps: SkillGap         = s["gaps"]
    letter: CoverLetter    = s.get("cover_letter")
    prep: InterviewPrep    = s.get("interview_prep")

    console.print(Rule(f"[bold cyan]AI Job Copilot — DEMO MODE[/bold cyan]"))
    console.print(f"[dim]Scenario: {s['label']}[/dim]\n")

    # ── Step 1: Parsed Job ────────────────────────────────────────────────────
    console.print(Rule("[bold]Step 1 — Job Parsed[/bold]"))
    t = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    t.add_column(style="dim", width=18)
    t.add_column()
    t.add_row("Company",   job.company)
    t.add_row("Role",      job.role)
    t.add_row("Location",  job.location)
    t.add_row("Market",    job.market)
    t.add_row("Seniority", job.seniority)
    t.add_row("Remote",    "Yes" if job.remote_ok else "No")
    t.add_row("Visa",      str(job.visa_sponsorship) if job.visa_sponsorship is not None else "Unknown")
    t.add_row("Salary",    job.salary_range or "Not stated")
    t.add_row("Stack",     ", ".join(job.tech_stack[:6]))
    console.print(t)

    # ── Step 2: Fit Score ─────────────────────────────────────────────────────
    console.print(Rule("[bold]Step 2 — Fit Score[/bold]"))
    vc = _verdict_color(score.verdict)
    body = Text()
    body.append(f"  Verdict  : ", style="bold")
    body.append(f"{score.verdict}\n", style=f"bold {vc}")
    body.append(f"  Score    : {_score_bar(score.score)}\n\n")
    body.append("  Strengths:\n", style="bold green")
    for s_ in score.strengths:
        body.append(f"    + {s_}\n", style="green")
    if score.gaps:
        body.append("\n  Gaps:\n", style="bold red")
        for g in score.gaps:
            body.append(f"    - {g}\n", style="red")
    body.append(f"\n  Reasoning: {score.reasoning}\n", style="dim")
    if score.risk_factors:
        body.append("\n  Risks:\n", style="bold yellow")
        for r in score.risk_factors:
            body.append(f"    ! {r}\n", style="yellow")
    if score.location_flag:
        body.append(f"\n  Location: {score.location_flag}\n", style="cyan")
    console.print(Panel(body, border_style=vc))

    # ── Step 3: Gap Analysis ──────────────────────────────────────────────────
    console.print(Rule("[bold]Step 3 — Skill Gap Analysis[/bold]"))
    g = gaps
    gbody = Text()
    if g.missing_skills:
        gbody.append("  Missing skills:\n", style="bold")
        for sk in g.missing_skills:
            gbody.append(f"    • {sk}\n")
        gbody.append("\n  Learning priority:\n", style="bold cyan")
        for i, sk in enumerate(g.learning_priority, 1):
            gbody.append(f"    {i}. {sk}\n", style="cyan")
        gbody.append("\n  Resources:\n", style="bold")
        for r in g.resources:
            gbody.append(f"    → {r}\n", style="dim")
        gbody.append(f"\n  Effort : {g.estimated_effort}\n", style="bold")
        gbody.append(f"  Impact : {g.score_impact}\n", style="bold green")
    else:
        gbody.append("  No significant gaps — strong match.\n", style="green")
    console.print(Panel(gbody, title="Skill Gap", border_style="blue"))

    # ── Step 4: Cover Letter ──────────────────────────────────────────────────
    if letter and score.verdict != Verdict.skip:
        console.print(Rule("[bold]Step 4 — Cover Letter[/bold]"))
        cbody = Text()
        cbody.append(f"Subject: {letter.subject_line}\n\n", style="bold")
        cbody.append(letter.body)
        cbody.append(f"\n\n[{letter.word_count} words]", style="dim")
        console.print(Panel(cbody, border_style="green"))

    # ── Step 5: Interview Prep ────────────────────────────────────────────────
    if prep and score.verdict != Verdict.skip:
        console.print(Rule("[bold]Step 5 — Interview Prep[/bold]"))
        pbody = Text()
        pbody.append("  Technical Questions:\n", style="bold cyan")
        for q in prep.likely_technical[:3]:
            pbody.append(f"    Q: {q}\n", style="cyan")
        pbody.append("\n  ML/AI Conceptual:\n", style="bold magenta")
        for q in prep.ml_ai_specific[:2]:
            pbody.append(f"    Q: {q}\n", style="magenta")
        pbody.append("\n  Red Flags to Address:\n", style="bold red")
        for rf in prep.red_flags_to_prepare_for:
            pbody.append(f"    ! {rf[:120]}...\n", style="red")
        if prep.company_research:
            pbody.append("\n  Company Research:\n", style="bold")
            pbody.append(f"    {prep.company_research[:300]}\n", style="dim")
        console.print(Panel(pbody, title="Interview Prep", border_style="magenta"))

    # ── Cost summary ──────────────────────────────────────────────────────────
    console.print(Rule())
    if score.verdict == Verdict.skip:
        console.print("[dim]Demo: Skip verdict — no documents generated. Cost ~$0.01[/dim]")
    else:
        console.print("[dim]Demo: Full pipeline run. Real cost ~$0.03 per application.[/dim]")
    console.print(
        "\n[bold]This is a demo run.[/bold] Real runs call Claude Sonnet (scoring/CV/cover letter) "
        "and Gemini Flash (parsing/gaps/interview prep)."
    )
    console.print("[dim]Run: python main.py analyze --market morocco[/dim]\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Job Copilot — Demo Mode")
    parser.add_argument(
        "--scenario", "-s",
        choices=list(DEMO_SCENARIOS.keys()),
        default="morocco",
        help="Which scenario to demo (default: morocco)",
    )
    args = parser.parse_args()
    run_demo(args.scenario)
