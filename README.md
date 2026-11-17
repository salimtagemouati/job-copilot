# AI Job Copilot

> **Apply to 10 roles intelligently, not 100 blindly.**

A personal AI career assistant that turns a raw job description into a tailored CV, cover letter, and interview prep in under 60 seconds — for ~$0.03 per application.

## Live Demo

```text
Step 1/5 — Parsing job description...
✓ OCP Group Digital | Junior AI/ML Engineer | Rabat, Morocco
Step 2/5 — Market filter: morocco passes automatically
Step 3/5 — Scoring fit...
Verdict: Maybe
Score: 62/100
Strengths:
  ✓ Strong alignment with core requirements: Python, FastAPI, LLM experience, Vector databases (FAISS), and REST API design
  ✓ DocuMind project directly showcases RAG SaaS experience
Gaps:
  ✗ Limited cloud experience (AWS/GCP/Azure) and no certifications
  ✗ No explicit experience with Docker mentioned in projects
  ✗ No production ML deployment at scale
Step 4/5 — Analyzing skill gaps...
Missing skills:
  • Docker
  • Cloud Experience (AWS/GCP/Azure)
  • Production ML Deployment
Estimated effort: 3-4 weeks part-time
Score impact: +10-15 points — would move verdict from Maybe to Strong Maybe/Hire
Step 5/5 — Generating documents (Maybe)...
✓ CV saved: outputs/pdfs/OCP_Group_Digital_Junior_AI_ML_Enginee_2026-04-17.pdf

Summary: OCP Group Digital | Junior AI/ML Engineer | Maybe (62/100)
CV: outputs/pdfs/OCP_Group_Digital_Junior_AI_ML_Enginee_2026-04-17.pdf
```

Built by [Salim Tagougui](https://salimtag.tech) as a production-grade portfolio project and daily job search tool.

---

## What it does

Paste a job description. The system runs a 6-step pipeline:

```
JD text / URL / file
        │
        ▼
1. parse_job()          Extract structured data  →  ParsedJob
        │
        ▼
2. market_filter()      Germany/Canada rules     →  eligible? (no LLM)
        │
        ▼
3. score_fit()          Realistic fit score      →  0-100, Apply/Maybe/Skip
        │
        ▼
4. analyze_gaps()       Exact skills to learn    →  always runs, even Skip
        │
        ▼
5. generate_docs()      CV + cover letter        →  only if Apply or Maybe
        │
        ▼
6. track()              SQLite application log   →  deduped by JD hash
```

**Sample output for a Morocco AI Engineer role:**

```
  Verdict  : Apply
  Score    : ████████████████░░░░░░  81/100

  Strengths:
    + DocuMind directly matches RAG pipeline requirement
    + FastAPI + Python stack alignment is exact
    + Junior/0-2 YOE level matches

  Gaps:
    - Docker not in current stack
    - No PostgreSQL production experience

  Missing skills  → Docker, PostgreSQL
  Learning path   → Docker: Play With Docker labs (~6h)
  Score impact    → +5 points with Docker added
```

---

## Architecture decisions

### Why two LLM providers?

Different tasks have different quality requirements:

| Task | Model | Why |
|------|-------|-----|
| `parse_job` | Gemini 2.5 Flash | Structured JSON extraction — deterministic, Gemini excels here |
| `score_fit` | Claude Sonnet | Nuanced judgment — wrong score sends you to wrong jobs |
| `analyze_gaps` | Gemini 2.5 Flash | List generation — fast and cheap |
| `tailor_cv` | Claude Sonnet | Your first impression — quality is non-negotiable |
| `cover_letter` | Claude Sonnet | Tone and precision matter — 150-250 word hard limit |
| `interview_prep` | Gemini 2.5 Flash | High-volume Q&A — speed over perfection |

**Result: ~80% cost reduction vs. Claude-only, with quality preserved on the tasks that decide whether you get the interview.**

All model assignments live in `.env` — no code changes to switch providers.

### Why no LangChain?

Plain Python functions with Jinja2 prompts. Every step is a function you can read, test, and debug in isolation. When a prompt breaks, you fix the `.j2` file and re-run. No framework magic between you and the output.

### Why SQLite?

Zero config, portable, sufficient for hundreds of applications. The tracker is the only stateful component — everything else is stateless functions. If this ever needs to scale, swapping SQLite for Postgres is a one-line change in `config.py`.

### Anti-hallucination constraints

The CV tailoring engine has a hard constraint: it can only reframe existing experience. If a required skill is not in Salim's profile, it flags `MISSING: skill` in `ats_keywords` instead of fabricating. The scoring engine has an anti-inflation guard: if the LLM returns a score > 75 with 3+ missing skills, it re-prompts once.

---

## Cost

Per full pipeline run (Apply verdict, all 6 steps):

```
parse_job       Gemini Flash    ~$0.0002
score_fit       Claude Sonnet   ~$0.009
analyze_gaps    Gemini Flash    ~$0.0003
tailor_cv       Claude Sonnet   ~$0.015
cover_letter    Claude Sonnet   ~$0.004
interview_prep  Gemini Flash    ~$0.001
─────────────────────────────────────────
Total (Apply)                   ~$0.030
Total (Skip)   (3 steps only)   ~$0.010
```

100 applications ≈ $2.50. Run `make cost` to see the full breakdown.

---

## Quick start

```bash
# 1. Clone and install
git clone https://github.com/salimtag/job-copilot
cd job-copilot
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env — add ANTHROPIC_API_KEY, GEMINI_API_KEY, TAVILY_API_KEY

# 3. Try the demo (no API keys needed)
make demo           # Morocco Apply scenario
make demo-germany   # Germany Maybe scenario
make demo-senior    # DeepMind Skip scenario — gap analysis only

# 4. Run for real
make analyze                          # paste a JD (Morocco, default)
make analyze-de                       # Germany strict filter applied
make analyze-url URL=https://...      # fetch from URL via Tavily

# 5. Track your applications
make tracker        # list all
make stats          # interview rate, avg score by market
make export         # CSV export
```

---

## CLI reference

```bash
# Analyze a JD
python main.py analyze --market morocco
python main.py analyze --market germany --url https://jobs.example.com/123
python main.py analyze --market remote --file ~/Downloads/jd.txt
python main.py analyze --market morocco --no-docs    # score + gaps only

# Search for jobs (Tavily)
python main.py search --market morocco
python main.py search --market germany --query "Junior ML Engineer Berlin English"
python main.py search --market remote --analyze     # auto-run pipeline on results

# Tracker
python main.py tracker list
python main.py tracker list --market germany --status Interview
python main.py tracker update 3 --status Interview --notes "Phone screen Monday 10am"
python main.py tracker stats
python main.py tracker export --output my_applications.csv
python main.py tracker delete 5

# FastAPI server
make serve    # http://localhost:8000/docs
```

---

## Market rules

The system applies different filters per market before scoring runs:

**Morocco** — no filter, apply standard scoring.

**Germany** — Salim does not speak German. A role must pass at least one of:
- JD is written in English
- Contains "English working language" / "international team"

Auto-rejected if any of these appear: `Deutschkenntnisse erforderlich`, `C1 Deutsch`, `Muttersprachler`, JD written entirely in German.

**Canada** — Must mention `LMIA`, `work permit sponsorship`, or `open to international applicants`.

**Remote** — no filter, apply standard scoring.

---

## Scoring

```
Skills match          30%
Tech stack alignment  25%
Experience level fit  20%
Role relevance        15%
Location / market     10%
```

| Score | Verdict | Action |
|-------|---------|--------|
| 70+   | Apply   | Full pipeline: CV + cover letter + interview prep |
| 45-69 | Maybe   | Full pipeline — apply with honest framing of gaps |
| < 45  | Skip    | Gap analysis only — use as learning roadmap |

**Anti-inflation guard:** If score > 75 with 3+ missing skills, the scorer re-prompts once with a calibration note. Calibrated scores are more useful than optimistic ones.

---

## Project structure

```
job_copilot/
├── main.py                    Typer CLI — entry point
├── config.py                  All settings, per-task model routing
├── Makefile                   One-command workflows
├── pyproject.toml             Python packaging
│
├── models/schemas.py          Pydantic schemas — single source of truth
│
├── ingestion/
│   ├── parser.py              LLM-based JD parser → ParsedJob
│   └── tavily_search.py       Tavily job search + company research
│
├── scoring/
│   ├── market_filter.py       Germany/Canada pre-filters (pure logic, no LLM)
│   └── engine.py              Fit scoring with anti-inflation guard
│
├── skill_gap/
│   └── analyzer.py            Actionable gap analysis (always runs)
│
├── cv_generator/
│   ├── tailor.py              CV tailoring (reframes only real experience)
│   ├── pdf_export.py          HTML → PDF via pdfkit
│   └── templates/             Jinja2 CV template
│
├── cover_letter/
│   └── generator.py           150-250 word hard limit, forbidden phrase check
│
├── interview_prep/
│   └── generator.py           Technical Q&A + Tavily company research
│
├── tracker/
│   ├── models.py              SQLModel Application table
│   └── db.py                  CRUD, stats, CSV export, dedup via SHA256
│
├── prompts/                   Jinja2 LLM prompt templates (*.j2)
│   ├── parse_job.j2
│   ├── score_fit.j2
│   ├── skill_gap.j2
│   ├── tailor_cv.j2
│   ├── cover_letter.j2
│   └── interview_prep.j2
│
├── utils/
│   ├── llm.py                 Unified Anthropic + Gemini router, retry, fallback
│   ├── logger.py              Structured logging with cost per call
│   └── validators.py          SHA256 dedup, word count helpers
│
├── api/
│   └── routes.py              FastAPI wrapper — REST API for all pipeline steps
│
├── demo/
│   └── run_demo.py            Full pipeline demo, zero API calls needed
│
└── tests/
    ├── fixtures/sample_jds.py Real JD fixtures (Morocco, Germany, Senior)
    └── test_core.py           35 tests — schemas, market filter, tracker, validators
```

---

## Tests

```bash
make test       # 35 tests, no LLM calls required
make test-cov   # with coverage report
```

All tests run without API keys — they cover:
- Pydantic schema validation and field constraints
- Germany/Canada market filter (8 test cases including edge cases)
- Tracker CRUD: create, dedup, update status, filter, stats, CSV export, delete
- Validator utilities: SHA256 hashing, word counting

---

## Stack

| Layer | Tool | Decision |
|-------|------|----------|
| LLM (quality tasks) | Anthropic Claude Sonnet | Scoring, CV, cover letter |
| LLM (volume tasks) | Google Gemini 2.5 Flash | Parsing, gaps, interview prep |
| Job search | Tavily API | No scraping, built for LLMs |
| Output validation | Pydantic v2 | Catches LLM hallucinations at runtime |
| API layer | FastAPI | Async, typed, OpenAPI docs free |
| Database | SQLite + SQLModel | Zero config, portable |
| PDF | pdfkit + wkhtmltopdf | Reliable HTML→PDF, no CSS pain |
| Templating | Jinja2 | Prompts AND HTML templates |
| CLI | Typer | Typed, built on Click |
| Config | pydantic-settings | .env → typed settings |

**Not using:** LangChain (abstraction hides errors), WeasyPrint (CSS rendering pain), Playwright (fragile scraping), OpenAI (wrong provider).

---

## Related projects

- [DocuMind](https://salimtag.tech/#documind) — RAG SaaS: FastAPI, Gemini, FAISS, Supabase, Stripe
- [BarberBook](https://salimtag.tech/#barberbook) — Mobile booking: React Native, FastAPI
- [Forest Fire Prediction](https://salimtag.tech/#forestfire) — YOLOv8, GIS data, FastAPI

---

*Built while job-seeking. The irony of building a job search tool instead of applying is not lost.*

### Local API access

Set `JOB_COPILOT_API_TOKEN` to a random value generated by `openssl rand -hex 32` before running `make serve`. Supply it using the Authorize button in the local API docs or the HTTP Authorization bearer header. The development server listens on 127.0.0.1. Keep this token private.
