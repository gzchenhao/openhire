"""Appendix-B regression suite (from the real-machine acceptance report 003).

Each real job_id pins a specific behavior that a v0.1 regression must never break. These
use deterministic seeded fixtures (the real ids + realistic attributes), so they encode
the CONTRACT independent of live ATS/LLM data:

  mongodb:7727896   — datePosted is the real ATS posting date; days_open reflects it.
  mongodb:7599693   — a services-sales role is role_family=sales and stays OUT of an
  datadog:7857714     engineering search (role_family filter + required_skills AND).
  openai:98ad…       — the write path works on an Ashby-hosted job (authorize_application).
  clickhouse:6001…   — a Netherlands, salary-less role survives min_salary by default and
                       is dropped only under require_stated_salary; remote_scope classifies.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from openhire import service
from openhire.db import Application, Company, Job, init_db, session_scope

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 7, 12, tzinfo=UTC)


def _job(jid, cid, title, skills, remote, location, *, posted=None, salary=None,
         role_family=None, apply_channel=None):
    smin, smax, cur = salary if salary else (None, None, None)
    return Job(
        id=jid, company_id=cid, title=title, description_raw=title,
        skills=skills, remote_policy=remote, location=location,
        salary_min=smin, salary_max=smax, salary_currency=cur,
        posted_at=posted, first_seen_at=NOW - dt.timedelta(days=2), verified_at=NOW,
        source="ats_public_api", ghost_score=0.0, role_family=role_family,
        apply_channel=apply_channel or f"https://boards.greenhouse.io/embed/job_app?for={cid}&token=x",
        content_hash=f"h{jid}",
    )


@pytest.fixture()
def appendix_b():
    init_db()
    with session_scope() as s:
        for t in (Application, Job, Company):
            for row in s.execute(select(t)).scalars():
                s.delete(row)
        s.flush()
        for cid, name, vendor in [
            ("mongodb", "MongoDB", "greenhouse"), ("datadog", "Datadog", "greenhouse"),
            ("openai", "OpenAI", "ashby"), ("clickhouse", "ClickHouse", "greenhouse"),
        ]:
            s.add(Company(id=cid, name=name, ats_vendor=vendor, ats_tenant=cid,
                          careers_url="x", last_crawled_at=NOW))
        s.add(_job("mongodb:7727896", "mongodb", "Security Software Engineer, Infrastructure",
                   ["rust", "k8s"], "remote", "Remote, US",
                   posted=NOW - dt.timedelta(days=110), salary=(127000, 249000, "USD"),
                   role_family="engineering"))
        s.add(_job("mongodb:7599693", "mongodb", "Engagement Manager (Services Sales)",
                   ["rust", "k8s"], "remote", "Remote, US", role_family="sales"))
        s.add(_job("datadog:7857714", "datadog", "Enterprise Sales Engineer - Rockies",
                   ["rust", "k8s"], "remote", "Remote, US", role_family="sales"))
        s.add(_job("openai:98ad9beb-4f91-496c-bd16-ac0b2a8d5bb2", "openai",
                   "Software Engineer, Infrastructure Security", ["rust", "k8s"], "remote",
                   "Remote", role_family="engineering",
                   apply_channel="https://jobs.ashbyhq.com/openai/98ad9beb-4f91-496c-bd16-ac0b2a8d5bb2/application"))
        s.add(_job("clickhouse:6001256004", "clickhouse", "Principal Software Engineer - Postgres",
                   ["rust", "postgres"], "remote", "Remote - Netherlands",
                   posted=NOW - dt.timedelta(days=30), role_family="engineering"))
    yield


def test_mongodb_7727896_dateposted_is_real(appendix_b):
    with session_scope() as s:
        job = s.get(Job, "mongodb:7727896")
        p = service.job_posting(job, s.get(Company, "mongodb"), ["rust", "k8s"], NOW)
    assert p["datePosted"] == (NOW - dt.timedelta(days=110)).date().isoformat()
    assert p["days_open"] == 110  # not the ~2-day crawl age


def test_sales_roles_excluded_from_engineering_search(appendix_b):
    with session_scope() as s:
        res = service.search_jobs(s, required_skills=["rust", "k8s"],
                                  role_family="engineering", now=NOW)
    ids = {r["job_id"] for r in res}
    assert "mongodb:7599693" not in ids   # services-sales
    assert "datadog:7857714" not in ids   # "Sales Engineer" — sales, not engineering
    assert "mongodb:7727896" in ids       # genuine engineering role stays
    assert all(r["role_family"] != "sales" for r in res)


def test_appendix_b_sales_ids_are_sales(appendix_b):
    with session_scope() as s:
        for jid in ("mongodb:7599693", "datadog:7857714"):
            assert s.get(Job, jid).role_family == "sales"


def test_openai_ashby_write_path(appendix_b):
    jid = "openai:98ad9beb-4f91-496c-bd16-ac0b2a8d5bb2"
    with session_scope() as s:
        out = service.apply(s, jid, "#a3f9", True, now=NOW)
    assert out["resume_transmitted"] is False
    assert out["apply_channel"].startswith("https://jobs.ashbyhq.com/openai/")
    assert out["receipt_id"].startswith("r_")


def test_clickhouse_netherlands_salaryless(appendix_b):
    jid = "clickhouse:6001256004"
    with session_scope() as s:
        # Default: a floor keeps the salary-less Dutch role (can't be ruled out).
        kept = {r["job_id"] for r in service.search_jobs(s, min_salary=600000, now=NOW)}
        assert jid in kept
        # require_stated_salary drops it.
        strict = {r["job_id"] for r in service.search_jobs(
            s, min_salary=600000, require_stated_salary=True, now=NOW)}
        assert jid not in strict
        # remote_scope classifies the Netherlands qualifier.
        job = s.get(Job, jid)
        p = service.job_posting(job, s.get(Company, "clickhouse"), ["rust"], NOW)
    assert p["remote_scope"] == "country_locked"
    assert "Netherlands" in p["eligible_regions"]
