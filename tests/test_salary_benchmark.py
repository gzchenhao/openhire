"""salary_benchmark (0.8.40, reports/118): employer-published ranges only, low and high ends
reported separately, never mixing currencies, no quantiles under 20 postings."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from openhire import service
from openhire.db.models import Base, Company, Job
from openhire.errors import OpenHireError

NOW = dt.datetime(2026, 10, 30, tzinfo=dt.timezone.utc)


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        for cid in ("waymo", "unitree"):
            s.add(Company(id=cid, name=cid, ats_vendor="greenhouse", ats_tenant=cid))
        rows = [("waymo", f"Senior Perception Engineer {i}", "USD", 150_000 + i * 1000, 200_000 + i * 1000, "annual") for i in range(25)]
        rows += [("unitree", f"运动控制工程师 {i}", "CNY", 20_000, 45_000, "monthly") for i in range(5)]
        for i, (cid, title, cur, lo, hi, period) in enumerate(rows):
            s.add(Job(id=f"{cid}:{i}", company_id=cid, title=title, description_raw="5+ years of experience",
                      source="ats_public_api", first_seen_at=NOW, verified_at=NOW, posted_at=NOW, skills=[],
                      location="SF", content_hash=f"h{i}", ghost_score=0.0, remote_policy="onsite",
                      salary_min=lo, salary_max=hi, salary_currency=cur, salary_period=period,
                      role_family="engineering", apply_channel="https://boards.greenhouse.io/x/jobs/1"))
        s.flush()
        yield s


def test_low_and_high_are_separate_and_currency_is_never_mixed(session):
    out = service.salary_benchmark(session, "usd", seniority=["senior"])
    assert out["postings"] == 25 and out["employers"] == 1
    assert out["annual_low"]["median"] == 162_000 and out["annual_high"]["median"] == 212_000
    assert "不是成交价" in out["in_words"]["zh"] and out["source"] == "employer_published_ranges"


def test_small_groups_get_a_count_and_no_quantiles_and_wide_ranges_are_counted(session):
    out = service.salary_benchmark(session, "CNY")
    assert out["postings"] == 5 and out["annual_low"] is None and out["wide_ranges"] == 5
    assert "少于 20 条" in out["in_words"]["zh"]


def test_years_filter_reads_the_posting_and_currency_is_required(session):
    assert service.salary_benchmark(session, "USD", years_min=6)["postings"] == 0
    assert service.salary_benchmark(session, "USD", years_min=3, years_max=5)["postings"] == 25
    with pytest.raises(OpenHireError):
        service.salary_benchmark(session, "")
