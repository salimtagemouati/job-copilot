"""
Test suite for AI Job Copilot.

Tests that don't require LLM calls (pure logic):
- Pydantic schema validation
- Market filter logic (pure Python)
- Tracker DB operations
- Validators and helpers

Run: PYTHONPATH=/path/to/job_copilot pytest tests/ -v
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from datetime import datetime, timezone

from models.schemas import (
    ParsedJob, FitScore, SkillGap, TailoredCV, CoverLetter,
    Market, Seniority, Verdict, ApplicationStatus,
)
from scoring.market_filter import (
    check_germany_eligibility,
    check_canada_eligibility,
    run_market_filter,
    get_germany_bonus_flags,
)
from utils.validators import hash_text, count_words
from tests.fixtures.sample_jds import (
    GERMANY_ENGLISH_JD, GERMANY_REJECTED_JD,
    PARSED_JOB_MOROCCO, PARSED_JOB_GERMANY, PARSED_JOB_SENIOR,
)


# ── Schema tests ───────────────────────────────────────────────────────────────

class TestSchemas:
    def test_parsed_job_valid(self):
        job = ParsedJob(**PARSED_JOB_MOROCCO)
        assert job.company == "Atlas Intelligence"
        assert job.market == Market.morocco
        assert job.seniority == Seniority.junior
        assert job.remote_ok is True

    def test_parsed_job_germany(self):
        job = ParsedJob(**PARSED_JOB_GERMANY)
        assert job.market == Market.germany
        assert job.visa_sponsorship is True
        assert job.salary_range is not None

    def test_fit_score_verdict_thresholds(self):
        score_apply = FitScore(
            score=75, verdict=Verdict.apply,
            strengths=["test"], gaps=[], reasoning="good",
            risk_factors=[],
        )
        assert score_apply.verdict == Verdict.apply

        score_maybe = FitScore(
            score=55, verdict=Verdict.maybe,
            strengths=[], gaps=["gap1"], reasoning="borderline",
            risk_factors=[],
        )
        assert score_maybe.verdict == Verdict.maybe

        score_skip = FitScore(
            score=30, verdict=Verdict.skip,
            strengths=[], gaps=["many gaps"], reasoning="not a fit",
            risk_factors=["requires 7+ YOE"],
        )
        assert score_skip.verdict == Verdict.skip

    def test_fit_score_range_validation(self):
        with pytest.raises(Exception):
            FitScore(score=101, verdict=Verdict.apply, strengths=[], gaps=[],
                     reasoning="", risk_factors=[])

        with pytest.raises(Exception):
            FitScore(score=-1, verdict=Verdict.apply, strengths=[], gaps=[],
                     reasoning="", risk_factors=[])

    def test_cover_letter_word_count_validation(self):
        # Valid: 200 words
        body = "word " * 200
        letter = CoverLetter(subject_line="Test Subject", body=body, word_count=200)
        assert letter.word_count == 200

        # Invalid: too short
        with pytest.raises(Exception):
            CoverLetter(subject_line="Test", body="short", word_count=5)

        # Invalid: too long
        with pytest.raises(Exception):
            CoverLetter(subject_line="Test", body="word " * 300, word_count=300)

    def test_skill_gap_valid(self):
        gap = SkillGap(
            missing_skills=["MLflow", "Docker"],
            learning_priority=["MLflow", "Docker"],
            resources=["MLflow: official docs", "Docker: Play with Docker labs"],
            estimated_effort="2 weeks part-time",
            score_impact="+12 points",
        )
        assert len(gap.missing_skills) == 2
        assert gap.estimated_effort == "2 weeks part-time"

    def test_application_status_enum(self):
        for status in ["Applied", "Interview", "Offer", "Rejected", "Ghosted"]:
            s = ApplicationStatus(status)
            assert s.value == status

    def test_market_enum(self):
        assert Market.morocco.value == "morocco"
        assert Market.germany.value == "germany"
        assert Market("remote") == Market.remote


# ── Market filter tests ────────────────────────────────────────────────────────

class TestGermanyFilter:
    def _make_job(self, raw_text: str, jd_language: str = "English") -> ParsedJob:
        return ParsedJob(
            company="TestCo",
            role="ML Engineer",
            location="Berlin, Germany",
            market=Market.germany,
            remote_ok=True,
            language_required="English",
            jd_language=jd_language,
            requirements=["Python"],
            nice_to_have=[],
            tech_stack=["Python"],
            seniority=Seniority.junior,
            raw_text=raw_text,
        )

    def test_english_jd_passes(self):
        job = ParsedJob(**PARSED_JOB_GERMANY)
        eligible, reason = check_germany_eligibility(job)
        assert eligible is True
        assert "Passed" in reason

    def test_german_required_rejects(self):
        job = self._make_job(GERMANY_REJECTED_JD, jd_language="German")
        eligible, reason = check_germany_eligibility(job)
        assert eligible is False

    def test_deutschkenntnisse_phrase_rejects(self):
        jd = "We need Python skills. Deutschkenntnisse erforderlich."
        job = self._make_job(jd, jd_language="German")
        eligible, reason = check_germany_eligibility(job)
        assert eligible is False
        # Rejected — either the jd_language=German shortcut OR the phrase match
        assert "German" in reason or "Deutschkenntnisse" in reason

    def test_c1_deutsch_rejects(self):
        jd = "Python developer role. C1 Deutsch required."
        job = self._make_job(jd)
        eligible, reason = check_germany_eligibility(job)
        assert eligible is False

    def test_international_team_passes(self):
        jd = "Python AI role in Berlin. International team. English is the working language."
        job = self._make_job(jd)
        eligible, reason = check_germany_eligibility(job)
        assert eligible is True

    def test_bonus_flags_detected(self):
        jd = (
            "Junior AI Engineer Berlin. English working language. "
            "Visa sponsorship available. EU Blue Card support. Relocation package included."
        )
        job = self._make_job(jd)
        bonuses = get_germany_bonus_flags(job)
        assert any("visa sponsorship" in b for b in bonuses)

    def test_german_jd_no_english_signal_rejects(self):
        jd = "Wir suchen Python-Entwickler. Sehr gute Deutschkenntnisse."
        job = self._make_job(jd, jd_language="German")
        eligible, reason = check_germany_eligibility(job)
        assert eligible is False

    def test_muttersprachler_rejects(self):
        jd = "Python developer. Muttersprachler Deutsch preferred."
        job = self._make_job(jd)
        eligible, reason = check_germany_eligibility(job)
        assert eligible is False


class TestCanadaFilter:
    def _make_canada_job(self, raw_text: str) -> ParsedJob:
        return ParsedJob(
            company="CanadaCo",
            role="ML Engineer",
            location="Montreal, Canada",
            market=Market.canada,
            remote_ok=False,
            language_required="English",
            jd_language="English",
            requirements=["Python"],
            nice_to_have=[],
            tech_stack=["Python"],
            seniority=Seniority.junior,
            raw_text=raw_text,
        )

    def test_lmia_passes(self):
        job = self._make_canada_job("ML Engineer Montreal. LMIA available.")
        eligible, reason = check_canada_eligibility(job)
        assert eligible is True

    def test_no_sponsorship_rejects(self):
        job = self._make_canada_job("ML Engineer Montreal. Great team. No visa support mentioned.")
        eligible, reason = check_canada_eligibility(job)
        assert eligible is False

    def test_work_permit_sponsorship_passes(self):
        job = self._make_canada_job("Python dev. Open to international applicants. Work permit sponsorship.")
        eligible, reason = check_canada_eligibility(job)
        assert eligible is True


class TestRunMarketFilter:
    def test_morocco_always_passes(self):
        job = ParsedJob(**PARSED_JOB_MOROCCO)
        eligible, reason = run_market_filter(job)
        assert eligible is True

    def test_remote_always_passes(self):
        job = ParsedJob(**{**PARSED_JOB_MOROCCO, "market": "remote", "raw_text": "remote job"})
        eligible, reason = run_market_filter(job)
        assert eligible is True


# ── Validator tests ────────────────────────────────────────────────────────────

class TestValidators:
    def test_hash_text_deterministic(self):
        text = "Hello World"
        assert hash_text(text) == hash_text(text)
        assert len(hash_text(text)) == 64  # SHA256 hex = 64 chars

    def test_hash_text_different_inputs(self):
        assert hash_text("hello") != hash_text("world")

    def test_count_words(self):
        assert count_words("hello world") == 2
        assert count_words("one two three four five") == 5
        assert count_words("") == 0   # empty string → 0

    def test_count_words_realistic(self):
        text = "word " * 200
        assert count_words(text.strip()) == 200


# ── Tracker DB tests ───────────────────────────────────────────────────────────

class TestTracker:
    @pytest.fixture(autouse=True)
    def setup_test_db(self, tmp_path, monkeypatch):
        """Use a fresh temp DB for each test."""
        db_file = tmp_path / "test_copilot.db"
        monkeypatch.setattr("config.settings.db_path", str(db_file))

        # Reset engine singleton for fresh DB
        import tracker.db as db_module
        db_module._engine = None

        from tracker.db import init_db
        init_db()
        yield
        db_module._engine = None

    def _make_job_and_score(self, suffix: str = ""):
        job = ParsedJob(
            company=f"TestCo{suffix}",
            role="Junior AI Engineer",
            location="Casablanca",
            market=Market.morocco,
            remote_ok=True,
            language_required="French",
            jd_language="French",
            requirements=["Python"],
            nice_to_have=[],
            tech_stack=["Python"],
            seniority=Seniority.junior,
            raw_text=f"Unique JD text {suffix} {datetime.now(timezone.utc)}",
        )
        score = FitScore(
            score=75, verdict=Verdict.apply,
            strengths=["Python"], gaps=[],
            reasoning="Good fit.", risk_factors=[],
        )
        return job, score

    def test_track_and_retrieve(self):
        from tracker.db import track_application, list_applications
        job, score = self._make_job_and_score("A")
        app = track_application(job, score, pdf_path="test.pdf")
        assert app is not None
        assert app.id is not None
        assert app.company == "TestCoA"
        assert app.score == 75
        assert app.status == "Applied"

        apps = list_applications()
        assert len(apps) == 1

    def test_duplicate_blocked(self):
        from tracker.db import track_application
        job, score = self._make_job_and_score("B")
        app1 = track_application(job, score)
        app2 = track_application(job, score)  # same raw_text = same hash
        assert app1 is not None
        assert app2 is None  # duplicate blocked

    def test_status_update(self):
        from tracker.db import track_application, update_status
        job, score = self._make_job_and_score("C")
        app = track_application(job, score)
        assert app is not None

        updated = update_status(app.id, "Interview", notes="Phone screen scheduled")
        assert updated is not None
        assert updated.status == "Interview"
        assert "Phone screen" in updated.notes

    def test_invalid_status_rejected(self):
        from tracker.db import track_application, update_status
        job, score = self._make_job_and_score("D")
        app = track_application(job, score)
        result = update_status(app.id, "InvalidStatus")
        assert result is None

    def test_filter_by_market(self):
        from tracker.db import track_application, list_applications
        job1, score1 = self._make_job_and_score("E1")
        job2 = ParsedJob(**{
            **PARSED_JOB_GERMANY,
            "raw_text": f"Germany JD unique {datetime.now(timezone.utc)}",
        })
        score2 = FitScore(score=70, verdict=Verdict.apply, strengths=[], gaps=[],
                          reasoning="ok", risk_factors=[])

        track_application(job1, score1)
        track_application(job2, score2)

        morocco_apps = list_applications(market="morocco")
        germany_apps = list_applications(market="germany")
        assert len(morocco_apps) == 1
        assert len(germany_apps) == 1

    def test_stats_empty(self):
        from tracker.db import get_stats
        stats = get_stats()
        assert stats.get("total") == 0

    def test_stats_with_data(self):
        from tracker.db import track_application, get_stats
        job, score = self._make_job_and_score("F")
        track_application(job, score)
        stats = get_stats()
        assert stats["total"] == 1
        assert stats["avg_score"] == 75.0
        assert "morocco" in stats["by_market"]

    def test_export_csv_format(self):
        from tracker.db import track_application, export_csv
        job, score = self._make_job_and_score("G")
        track_application(job, score)
        csv_data = export_csv()
        assert "company" in csv_data  # header
        assert "TestCoG" in csv_data  # data row

    def test_duplicate_detection_helper(self):
        from tracker.db import track_application, check_duplicate
        job, score = self._make_job_and_score("H")
        assert check_duplicate(job.raw_text) is None
        track_application(job, score)
        dup = check_duplicate(job.raw_text)
        assert dup is not None
        assert dup.company == "TestCoH"

    def test_delete_application(self):
        from tracker.db import track_application, delete_application, get_application
        job, score = self._make_job_and_score("I")
        app = track_application(job, score)
        assert app is not None
        deleted = delete_application(app.id)
        assert deleted is True
        assert get_application(app.id) is None
