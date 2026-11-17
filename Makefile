# AI Job Copilot — Makefile
# Usage: make <target>
# Requires: Python 3.10+, pip install -r requirements.txt

PYTHON     = python
PYTHONPATH = PYTHONPATH=.
CLI        = $(PYTHONPATH) $(PYTHON) main.py

.DEFAULT_GOAL := help

# ── Help ───────────────────────────────────────────────────────────────────────
.PHONY: help
help:
	@echo ""
	@echo "  AI Job Copilot"
	@echo "  ─────────────────────────────────────────────────"
	@echo "  make setup          Install deps + verify config"
	@echo "  make demo           Run demo (no API keys needed)"
	@echo "  make demo-germany   Demo: Germany scenario"
	@echo "  make demo-senior    Demo: Skip scenario"
	@echo "  make analyze        Analyze a job (Morocco, paste JD)"
	@echo "  make analyze-de     Analyze a Germany job"
	@echo "  make analyze-url    Analyze from URL (set URL=...)"
	@echo "  make search         Search Morocco market"
	@echo "  make search-de      Search Germany (English roles only)"
	@echo "  make tracker        Show tracked applications"
	@echo "  make stats          Show application stats"
	@echo "  make export         Export tracker to CSV"
	@echo "  make serve          Start FastAPI server (port 8000)"
	@echo "  make test           Run all tests"
	@echo "  make test-cov       Run tests with coverage report"
	@echo "  make lint           Check code style (ruff)"
	@echo "  make clean          Remove __pycache__ and output files"
	@echo "  make cost           Estimate cost for one full pipeline run"
	@echo ""

# ── Setup ──────────────────────────────────────────────────────────────────────
.PHONY: setup
setup:
	@echo "Installing dependencies..."
	pip install -r requirements.txt
	@echo ""
	@echo "Verifying config..."
	$(PYTHONPATH) $(PYTHON) config.py
	@echo ""
	@echo "Setup complete. Next: cp .env.example .env and add your API keys."

# ── Demo (zero API keys needed) ────────────────────────────────────────────────
.PHONY: demo demo-germany demo-senior
demo:
	$(PYTHONPATH) $(PYTHON) demo/run_demo.py --scenario morocco

demo-germany:
	$(PYTHONPATH) $(PYTHON) demo/run_demo.py --scenario germany

demo-senior:
	$(PYTHONPATH) $(PYTHON) demo/run_demo.py --scenario senior

# ── Analyze ────────────────────────────────────────────────────────────────────
.PHONY: analyze analyze-de analyze-ca analyze-remote analyze-url
analyze:
	$(CLI) analyze --market morocco

analyze-de:
	$(CLI) analyze --market germany

analyze-ca:
	$(CLI) analyze --market canada

analyze-remote:
	$(CLI) analyze --market remote

analyze-url:
	$(CLI) analyze --market morocco --url "$(URL)"

analyze-file:
	$(CLI) analyze --market morocco --file "$(FILE)"

# ── Search ─────────────────────────────────────────────────────────────────────
.PHONY: search search-de search-remote
search:
	$(CLI) search --market morocco

search-de:
	$(CLI) search --market germany --query "Junior AI Engineer Berlin English speaking visa sponsorship"

search-remote:
	$(CLI) search --market remote --query "Junior AI Engineer remote worldwide"

# ── Tracker ────────────────────────────────────────────────────────────────────
.PHONY: tracker stats export
tracker:
	$(CLI) tracker list

tracker-de:
	$(CLI) tracker list --market germany

tracker-interview:
	$(CLI) tracker list --status Interview

stats:
	$(CLI) tracker stats

export:
	$(CLI) tracker export --output tracker_export.csv
	@echo "Exported to tracker_export.csv"

# ── API Server ─────────────────────────────────────────────────────────────────
.PHONY: serve
serve:
	$(PYTHONPATH) uvicorn api.routes:app --reload --port 8000 --host 127.0.0.1

# ── Tests ──────────────────────────────────────────────────────────────────────
.PHONY: test test-cov test-fast
test:
	$(PYTHONPATH) $(PYTHON) -m pytest tests/ -v

test-fast:
	$(PYTHONPATH) $(PYTHON) -m pytest tests/ -q

test-cov:
	$(PYTHONPATH) $(PYTHON) -m pytest tests/ --cov=. --cov-report=term-missing --cov-report=html
	@echo "Coverage report: htmlcov/index.html"

# ── Code quality ───────────────────────────────────────────────────────────────
.PHONY: lint format
lint:
	@command -v ruff >/dev/null 2>&1 || pip install ruff -q
	ruff check .

format:
	@command -v ruff >/dev/null 2>&1 || pip install ruff -q
	ruff format .

# ── Utilities ──────────────────────────────────────────────────────────────────
.PHONY: cost clean
cost:
	@echo ""
	@echo "  Estimated cost per pipeline run (April 2025 pricing):"
	@echo "  ──────────────────────────────────────────────────────"
	@echo "  parse_job      Gemini 2.5 Flash   ~\$$0.0002"
	@echo "  score_fit      Claude Sonnet       ~\$$0.009"
	@echo "  skill_gap      Gemini 2.5 Flash   ~\$$0.0003"
	@echo "  tailor_cv      Claude Sonnet       ~\$$0.015"
	@echo "  cover_letter   Claude Sonnet       ~\$$0.004"
	@echo "  interview_prep Gemini 2.5 Flash   ~\$$0.001"
	@echo "  ──────────────────────────────────────────────────────"
	@echo "  Apply verdict  (all 6 steps)       ~\$$0.030"
	@echo "  Skip verdict   (parse+score+gaps)  ~\$$0.010"
	@echo ""
	@echo "  100 applications (mix of Apply/Skip) ≈ \$$2.50"
	@echo ""

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -f job_copilot.db
	rm -rf outputs/pdfs/* outputs/html/*
	rm -rf htmlcov/ .coverage
	@echo "Cleaned."
