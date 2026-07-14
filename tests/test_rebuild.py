"""Rebuild pipeline — cost math, fallback preservation, cost ceiling, rollback.

Uses the global temp DB (conftest) with a mocked DeepSeek extractor (no network).
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from openhire import config
from openhire.db import Job, init_db, session_scope
from openhire.db.models import Company
from openhire.pipeline import rebuild
from openhire.pipeline.extract import DeepSeekExtractor, ExtractionResult, make_deepseek_extractor

UTC = dt.timezone.utc


class FakeDeepSeek:
    """Deterministic stand-in: returns a fixed extraction + fixed token usage."""

    def __init__(self, skills=("go", "cuda"), remote="hybrid", tokens=(1000, 50)):
        self._skills = list(skills)
        self._remote = remote
        self._tok = tokens

    def extract_with_usage(self, rec):
        return (
            ExtractionResult(skills=self._skills, remote_policy=self._remote,
                             salary_min=None, salary_max=None, salary_currency=None),
            self._tok[0], self._tok[1],
        )


@pytest.fixture()
def seeded_jobs():
    init_db()
    now = dt.datetime.now(UTC)
    with session_scope() as s:
        for t in (Job, Company):
            for row in s.execute(select(t)).scalars():
                s.delete(row)
        s.flush()
        s.add(Company(id="acme", name="Acme", ats_vendor="greenhouse", ats_tenant="acme",
                      careers_url="x", last_crawled_at=now))
        for i in range(10):
            s.add(Job(
                id=f"acme:{i}", company_id="acme", title=f"Role {i}",
                description_raw="rust k8s", skills=["rust", "k8s"], remote_policy="remote",
                first_seen_at=now, verified_at=now, source="ats_public_api",
                apply_channel="https://x", content_hash=f"h{i}", ghost_score=0.0,
                extraction_source="heuristic",
            ))
    return now


def test_cost_math():
    # 1M input @ ¥2, 1M output @ ¥8
    assert rebuild.cost_cny(1_000_000, 0) == pytest.approx(config.DEEPSEEK_PRICE_INPUT_CNY)
    assert rebuild.cost_cny(0, 1_000_000) == pytest.approx(config.DEEPSEEK_PRICE_OUTPUT_CNY)


def test_rebuild_preserves_heuristic_in_fallback(seeded_jobs, monkeypatch):
    monkeypatch.setattr(rebuild, "make_deepseek_extractor", lambda: FakeDeepSeek())
    stats = rebuild.rebuild_extraction(batch_size=5, workers=2, ceiling_cny=999)
    assert stats.updated == 10 and stats.failed == 0
    with session_scope() as s:
        job = s.get(Job, "acme:0")
        assert job.extraction_source == "deepseek"
        assert set(job.skills) == {"go", "cuda"}          # skills → LLM (the win)
        assert set(job.skills_fallback) == {"rust", "k8s"}  # heuristic preserved
        # remote was a known ATS value → merge KEEPS it (LLM's "hybrid" is ignored).
        assert job.remote_policy == "remote"
        assert job.remote_policy_fallback == "remote"


def test_merge_policy_keeps_authoritative_and_fills_gaps():
    from types import SimpleNamespace as NS

    from openhire.pipeline.rebuild import _JobOutcome, merge_extraction

    oc = _JobOutcome("x", True, skills=["go", "cuda"], remote_policy="hybrid",
                     salary_min=1, salary_max=2, salary_currency="EUR")
    # Known remote + known salary → kept; skills always from the LLM.
    known = NS(remote_policy="remote", salary_min=100000, salary_max=150000,
               salary_currency="USD")
    m = merge_extraction(known, oc)
    assert m.skills == ["go", "cuda"]
    assert m.remote_policy == "remote"
    assert (m.salary_min, m.salary_max, m.salary_currency) == (100000, 150000, "USD")
    # Unknown remote + no salary → filled from the LLM.
    gap = NS(remote_policy="unknown", salary_min=None, salary_max=None, salary_currency=None)
    m2 = merge_extraction(gap, oc)
    assert m2.remote_policy == "hybrid"
    assert (m2.salary_min, m2.salary_max) == (1, 2)


def test_rebuild_is_resumable(seeded_jobs, monkeypatch):
    monkeypatch.setattr(rebuild, "make_deepseek_extractor", lambda: FakeDeepSeek())
    # First run only does 4.
    rebuild.rebuild_extraction(batch_size=2, workers=2, limit=4, ceiling_cny=999)
    with session_scope() as s:
        done = s.scalar(select(__import__("sqlalchemy").func.count()).select_from(Job)
                        .where(Job.extraction_source == "deepseek"))
    assert done == 4
    # Second run finishes the remaining 6 (skips already-converted rows).
    stats = rebuild.rebuild_extraction(batch_size=5, workers=2, ceiling_cny=999)
    assert stats.total_target == 6 and stats.updated == 6


def test_rebuild_halts_at_cost_ceiling(seeded_jobs, monkeypatch):
    monkeypatch.setattr(rebuild, "make_deepseek_extractor", lambda: FakeDeepSeek())
    # Each job ~¥0.0024; a tiny ceiling must halt after the first batch.
    stats = rebuild.rebuild_extraction(batch_size=3, workers=2, ceiling_cny=0.001)
    assert stats.halted is True
    assert "ceiling" in stats.halt_reason
    assert stats.processed == 3  # stopped after the first committed batch


def test_rollback_restores_heuristic(seeded_jobs, monkeypatch):
    monkeypatch.setattr(rebuild, "make_deepseek_extractor", lambda: FakeDeepSeek())
    rebuild.rebuild_extraction(batch_size=5, workers=2, ceiling_cny=999)
    n = rebuild.rollback_extraction()
    assert n == 10
    with session_scope() as s:
        job = s.get(Job, "acme:3")
        assert job.extraction_source == "heuristic"
        assert set(job.skills) == {"rust", "k8s"}  # restored
        assert job.remote_policy == "remote"


def test_deepseek_parses_and_prefers_structured_salary():
    ext = DeepSeekExtractor("k", "https://api.deepseek.com", "deepseek-chat")
    from openhire.ats.base import JobRecord
    job = JobRecord(ats_job_id="1", title="Eng", description_raw="d",
                    apply_channel="x", salary_min=100000, salary_max=150000,
                    salary_currency="USD")
    res = ext._to_result(
        {"skills": ["Rust", "K8S"], "remote_policy": "remote",
         "salary_min": 999, "salary_max": 999, "salary_currency": "EUR"}, job)
    assert res.skills == ["rust", "k8s"]           # lowercased
    assert res.remote_policy == "remote"
    assert (res.salary_min, res.salary_max, res.salary_currency) == (100000, 150000, "USD")


def test_make_deepseek_requires_key(monkeypatch):
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", None)
    with pytest.raises(RuntimeError):
        make_deepseek_extractor()
