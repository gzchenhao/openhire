"""get_company_info says whether an employer's posting dates are the employer's own.

Per row, `date_signal: "not_reported_by_ats"` marks a posting aged from the day this index
first saw it. The aggregate needs the same flag: Li Auto's first-party mirror carries no
date at all, so its median_days_open and ghost_score_avg are lower bounds on age, and a
caller reading them as the employer's timeline would be reading something we never had.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from openhire import service
from openhire.db.models import Base, Company, Job

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 9, 23, tzinfo=UTC)
EARLIER = dt.datetime(2026, 9, 1, tzinfo=UTC)


def _job(jid: str, company: str, posted_at, delisted_at=None) -> Job:
    return Job(
        id=jid, company_id=company, title="感知算法工程师", description_raw="x",
        skills=["bev"], remote_policy="onsite", location="Beijing",
        posted_at=posted_at, first_seen_at=EARLIER, verified_at=NOW, delisted_at=delisted_at,
        source="ats_public_api", apply_channel=f"https://www.lixiang.com/employ/detail/{jid}.html",
        content_hash=f"h{jid}", ghost_score=0.0, role_family="engineering",
    )


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        s.add(Company(id="lixiang", name="理想汽车 Li Auto", ats_vendor="lixiang",
                      ats_tenant="social", careers_url="x", last_crawled_at=NOW))
        s.add(Company(id="acme", name="Acme AI", ats_vendor="greenhouse",
                      ats_tenant="acme", careers_url="y", last_crawled_at=NOW))
        s.add(_job("l1", "lixiang", None))
        s.add(_job("l2", "lixiang", None))
        s.add(_job("l3", "lixiang", EARLIER, delisted_at=NOW))  # delisted rows do not count
        s.add(_job("a1", "acme", EARLIER))
        s.add(_job("a2", "acme", None))
        s.commit()
        yield s


def test_an_employer_whose_source_reports_no_date_says_so(session):
    info = service.get_company_info(session, "lixiang", now=NOW)
    assert info["active_jobs"] == 2
    assert info["posting_dates_reported"] is False
    assert info["postings_without_reported_date"] == 2
    # Aged from first sight, so a number is still reported; it is a lower bound.
    assert info["median_days_open"] == 22


def test_one_reported_date_is_enough_to_flip_the_flag(session):
    info = service.get_company_info(session, "acme", now=NOW)
    assert info["active_jobs"] == 2
    assert info["posting_dates_reported"] is True
    assert info["postings_without_reported_date"] == 1


def test_the_same_rule_as_the_per_row_date_signal(session):
    rows = service.search_jobs(session, ["bev"], None, 0.0, 10, company="lixiang")
    assert rows and all(r.get("date_signal") == "not_reported_by_ats" for r in rows)
    rows = service.search_jobs(session, ["bev"], None, 0.0, 10, company="acme")
    flagged = {r["job_id"]: r.get("date_signal") for r in rows}
    assert flagged == {"a1": None, "a2": "not_reported_by_ats"}


def test_a_name_lookup_aggregates_the_resolved_employer(session):
    # Resolving a name to a Company row and then counting jobs under the raw name string
    # gave zeros for every aggregate; the aggregates must key on the resolved id.
    info = service.get_company_info(session, "理想", now=NOW)
    assert info["company_id"] == "lixiang"
    assert info["active_jobs"] == 2 and info["postings_without_reported_date"] == 2
