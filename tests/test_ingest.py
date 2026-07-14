"""Pipeline logic tests — hermetic (in-memory SQLite, no network).

Covers change detection, delist, relist inheritance, ghost_score recompute, and — most
importantly for M1 acceptance — that every ingested job carries all five protocol
fields (with response_sla_days legally NULL).
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from openhire.ats.base import FetchResult, JobRecord
from openhire.db.models import Base, Company, Job
from openhire.pipeline.extract import HeuristicExtractor
from openhire.pipeline.ingest import IngestStats, ingest_company

UTC = dt.timezone.utc


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        s.add(
            Company(
                id="acme",
                name="Acme AI",
                ats_vendor="greenhouse",
                ats_tenant="acme",
                careers_url="https://job-boards.greenhouse.io/acme",
            )
        )
        s.commit()
        yield s


def rec(job_id: str, title: str, desc: str = "We use Rust, Kubernetes and RAG.", **kw):
    return JobRecord(
        ats_job_id=job_id,
        title=title,
        description_raw=desc,
        apply_channel=f"https://job-boards.greenhouse.io/acme/jobs/{job_id}",
        location=kw.get("location", "Remote - US"),
        remote_hint=kw.get("remote_hint", "remote"),
    )


def company(session) -> Company:
    return session.get(Company, "acme")


def ingest(session, records, now):
    stats = IngestStats()
    ingest_company(
        session, company(session), FetchResult(ok=True, status=200, records=records),
        HeuristicExtractor(), stats, now=now,
    )
    session.flush()
    return stats


def test_new_job_has_all_five_protocol_fields(session):
    now = dt.datetime(2026, 7, 1, tzinfo=UTC)
    ingest(session, [rec("1", "LLM Platform Engineer")], now)

    job = session.get(Job, "acme:1")
    # ① verified_at
    assert job.verified_at is not None
    # ② source — first-party only
    assert job.source == "ats_public_api"
    # ③ ghost_score present and in range
    assert job.ghost_score is not None and 0 <= job.ghost_score <= 1
    # ④ response_sla_days — NULL is legal in v0.1
    assert job.response_sla_days is None
    # ⑤ apply_channel — the employer's own URL
    assert job.apply_channel.startswith("https://job-boards.greenhouse.io/acme")
    # extraction populated skills + remote
    assert "rust" in job.skills and "k8s" in job.skills and "rag" in job.skills
    assert job.remote_policy == "remote"
    assert job.salary_inferred is False


def test_unchanged_refreshes_verified_at_only(session):
    t0 = dt.datetime(2026, 7, 1, tzinfo=UTC)
    ingest(session, [rec("1", "LLM Platform Engineer")], t0)
    hash0 = session.get(Job, "acme:1").content_hash

    t1 = dt.datetime(2026, 7, 2, tzinfo=UTC)
    stats = ingest(session, [rec("1", "LLM Platform Engineer")], t1)

    job = session.get(Job, "acme:1")
    assert stats.jobs_unchanged == 1
    assert stats.extractions == 0  # no re-extraction when hash is stable
    assert job.content_hash == hash0
    assert job.verified_at == t1  # ① refreshed


def test_content_change_triggers_reextraction(session):
    t0 = dt.datetime(2026, 7, 1, tzinfo=UTC)
    ingest(session, [rec("1", "LLM Platform Engineer", "We use Rust.")], t0)

    t1 = dt.datetime(2026, 7, 3, tzinfo=UTC)
    stats = ingest(session, [rec("1", "LLM Platform Engineer", "We use Go and CUDA.")], t1)

    job = session.get(Job, "acme:1")
    assert stats.jobs_updated == 1
    assert stats.extractions == 1
    assert "go" in job.skills and "cuda" in job.skills


def test_delist_marks_row_not_deletes(session):
    t0 = dt.datetime(2026, 7, 1, tzinfo=UTC)
    ingest(session, [rec("1", "Role A"), rec("2", "Role B")], t0)

    t1 = dt.datetime(2026, 7, 5, tzinfo=UTC)
    stats = ingest(session, [rec("1", "Role A")], t1)  # Role B vanished

    b = session.get(Job, "acme:2")
    assert stats.jobs_delisted == 1
    assert b is not None  # row kept
    assert b.delisted_at == t1


def test_relist_inherits_first_seen_and_increments(session):
    t0 = dt.datetime(2026, 5, 1, tzinfo=UTC)
    ingest(session, [rec("1", "Staff LLM Engineer")], t0)

    # Delist it.
    t1 = dt.datetime(2026, 6, 1, tzinfo=UTC)
    ingest(session, [], t1)
    assert session.get(Job, "acme:1").delisted_at == t1

    # A NEW id with the same normalized title reappears → relist.
    t2 = dt.datetime(2026, 7, 1, tzinfo=UTC)
    stats = ingest(session, [rec("99", "Staff  LLM  Engineer")], t2)

    new = session.get(Job, "acme:99")
    assert stats.jobs_relisted == 1
    assert new.relist_count == 1
    assert new.first_seen_at == t0  # inherited from the original posting
    # ghost_score reflects the relist term (0.15) + long staleness.
    assert new.ghost_score >= 0.15


def test_same_id_reappearing_is_revived_not_relisted(session):
    t0 = dt.datetime(2026, 6, 1, tzinfo=UTC)
    ingest(session, [rec("1", "Role A")], t0)
    ingest(session, [], dt.datetime(2026, 6, 2, tzinfo=UTC))  # delist
    assert session.get(Job, "acme:1").delisted_at is not None

    stats = ingest(session, [rec("1", "Role A")], dt.datetime(2026, 6, 3, tzinfo=UTC))
    job = session.get(Job, "acme:1")
    assert job.delisted_at is None  # revived
    assert job.relist_count == 0  # not counted as a relist
    assert stats.jobs_relisted == 0


def test_ghost_score_grows_with_age(session):
    t0 = dt.datetime(2026, 1, 1, tzinfo=UTC)
    ingest(session, [rec("1", "Role A")], t0)
    early = session.get(Job, "acme:1").ghost_score

    # Re-crawl 200 days later; staleness term kicks in.
    ingest(session, [rec("1", "Role A")], dt.datetime(2026, 7, 20, tzinfo=UTC))
    late = session.get(Job, "acme:1").ghost_score
    assert late > early


def test_failed_fetch_does_not_touch_jobs(session):
    t0 = dt.datetime(2026, 7, 1, tzinfo=UTC)
    ingest(session, [rec("1", "Role A")], t0)

    stats = IngestStats()
    ingest_company(
        session, company(session),
        FetchResult(ok=False, status=404, error="non-200"),
        HeuristicExtractor(), stats, now=dt.datetime(2026, 7, 2, tzinfo=UTC),
    )
    session.flush()
    assert stats.companies_failed == 1
    # Existing job untouched (not delisted by a failed crawl).
    assert session.get(Job, "acme:1").delisted_at is None
