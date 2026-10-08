"""Employer self-reported rosters (`ats/self_reported.py`): hermetic, no network.

The adapter is the door for employers with no readable system (reports/060), and the
tests pin the four conditions that keep it from becoming a job board:
  * a row without a date is not indexed, and a row older than MAX_AGE_DAYS (per renewal)
    is dropped, so nothing lives on by inertia;
  * the apply link is handed over only on the employer's own https domain, else the
    seeker is sent to the careers page we verified;
  * every row is marked as self-reported: `source` and `date_signal` say so;
  * nothing about ranking changes (the record shape is the same JobRecord as every ATS).
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib

import pytest

from openhire.ats import all_vendors, apply_url_is_trusted, get_client
from openhire.ats import self_reported as sr
from openhire.seed import all_candidates, candidate_count
from openhire.seed.candidates import _SELF_REPORTED

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "self_reported_roster.json"
ROSTER = json.loads(FIXTURE.read_text(encoding="utf-8"))
NOW = dt.datetime(2026, 10, 8, tzinfo=dt.timezone.utc)
SLUG = "example-robotics"


@pytest.fixture()
def registered(monkeypatch):
    """Register the fixture employer for the duration of a test, the way a real entry
    would be declared in SELF_REPORTED_EMPLOYERS after identity verification."""
    emp = sr.SelfReportedEmployer(
        slug=SLUG, name=ROSTER["name"], domain=ROSTER["domain"],
        careers_url=ROSTER["careers_url"], verified_on=ROSTER["verified_on"],
        verification="test fixture: gsxt, ICP, domain age, callback all pretend",
    )
    monkeypatch.setitem(sr.SELF_REPORTED_EMPLOYERS, SLUG, emp)
    return emp


# --- registry and seed ------------------------------------------------------------
def test_registered_as_a_vendor():
    assert "self_reported" in all_vendors()
    assert isinstance(get_client("self_reported"), sr.SelfReportedClient)


def test_seed_rows_are_derived_from_the_declared_employers():
    """One place to add an employer: the adapter's registry. The candidate list mirrors it."""
    assert [(c.tenant, c.name) for c in _SELF_REPORTED] == [
        (e.slug, e.name) for e in sr.SELF_REPORTED_EMPLOYERS.values()
    ]
    rows = [c for c in all_candidates() if c.vendor == "self_reported"]
    assert len(rows) == len(sr.SELF_REPORTED_EMPLOYERS)
    # A declared employer must say what was verified; an empty field is a registration
    # that skipped the ladder (reports/064).
    for e in sr.SELF_REPORTED_EMPLOYERS.values():
        assert e.verification.strip() and e.verified_on, e.slug
    assert candidate_count() == len(all_candidates())


def test_careers_url_is_the_employers_own_page_when_declared(registered):
    client = sr.SelfReportedClient()
    assert client.careers_url(SLUG) == "https://www.example-robotics.cn/careers"
    assert client.endpoint(SLUG).startswith("https://raw.githubusercontent.com/gzchenhao/openhire/main/employers/")
    assert client.endpoint(SLUG).endswith("example-robotics.json")


# --- parsing: the four conditions ----------------------------------------------------
def test_expired_and_undated_rows_are_dropped_and_renewal_keeps_a_row(registered):
    records = sr.SelfReportedClient().parse(ROSTER, SLUG, now=NOW)
    titles = [r.title for r in records]
    assert "感知算法工程师" in titles
    assert "嵌入式软件工程师" in titles
    assert "机器人产品经理" in titles          # posted in May, renewed 2026-10-05
    assert "运动控制算法工程师" not in titles   # posted in May, never renewed
    assert "没有日期的岗位" not in titles
    assert len(records) == 3


def test_apply_link_only_on_the_employers_own_https_domain(registered):
    by_title = {r.title: r for r in sr.SelfReportedClient().parse(ROSTER, SLUG, now=NOW)}
    own = by_title["感知算法工程师"]
    assert own.apply_channel == "https://www.example-robotics.cn/careers/perception"
    assert apply_url_is_trusted(own.apply_channel, "self_reported", extra_hosts=sr.trusted_hosts(SLUG))
    # A link on someone else's host is not handed over; the seeker gets the careers page.
    foreign = by_title["嵌入式软件工程师"]
    assert foreign.apply_channel == "https://www.example-robotics.cn/careers"
    assert "投递邮箱：hr@example-robotics.cn" in foreign.description_raw
    # Without the employer's domain the generic trust check still refuses an unknown host.
    assert not apply_url_is_trusted("https://www.example-robotics.cn/careers/perception")


def test_dates_salary_and_ids_come_from_the_roster(registered):
    by_title = {r.title: r for r in sr.SelfReportedClient().parse(ROSTER, SLUG, now=NOW)}
    own = by_title["感知算法工程师"]
    assert own.ats_job_id == "perception-sh"
    assert own.posted_at == dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc)
    assert (own.salary_min, own.salary_max, own.salary_currency, own.salary_period) == (
        25000, 40000, "CNY", "monthly"
    )
    pm = by_title["机器人产品经理"]
    assert pm.posted_at.date().isoformat() == "2026-05-01"
    assert pm.updated_at.date().isoformat() == "2026-10-05"
    # A row without an id gets a stable one from (tenant, title, location, date).
    assert len(pm.ats_job_id) == 12
    assert pm.ats_job_id == sr.SelfReportedClient().parse(ROSTER, SLUG, now=NOW)[2].ats_job_id


def test_an_unregistered_slug_hands_over_nothing_without_a_domain():
    """No declared employer means no domain to trust and no careers page to fall back to,
    so a roster that appears without its registration yields no rows at all."""
    assert sr.SelfReportedClient().parse(ROSTER, "nobody", now=NOW) == []


# --- the row says what it is -----------------------------------------------------------
def test_rows_are_marked_self_reported_in_source_and_date_signal(registered):
    from openhire import service
    from openhire.db.models import Company, Job
    from openhire.pipeline import ingest

    company = Company(id=SLUG, name=ROSTER["name"], ats_vendor="self_reported",
                      ats_tenant=SLUG, careers_url=ROSTER["careers_url"], verified=False)
    assert ingest.source_for(company) == "employer_self_reported"
    ats_company = Company(id="waymo", name="Waymo", ats_vendor="greenhouse",
                          ats_tenant="waymo", careers_url="x", verified=False)
    assert ingest.source_for(ats_company) == "ats_public_api"

    job = Job(id=f"{SLUG}:perception-sh", company_id=SLUG, title="感知算法工程师",
              description_raw="x", skills=["perception"], remote_policy="onsite",
              location="上海", posted_at=NOW, first_seen_at=NOW, verified_at=NOW,
              source="employer_self_reported", apply_channel=ROSTER["postings"][0]["apply_url"],
              content_hash="h", ghost_score=0.0, role_family="engineering")
    assert service.date_signal_for(job, company) == "self_reported"
    assert service.date_signal_for(job, ats_company) is None
    job.posted_at = None
    assert service.date_signal_for(job, ats_company) == "not_reported_by_ats"
    # A self-reported roster row that somehow lost its date is aged from first sight too.
    assert service.date_signal_for(job, company) == "not_reported_by_ats"
    job.posted_at = NOW
    row = service.job_posting(job, company, [], NOW)
    assert row["source"] == "employer_self_reported"
    assert row["date_signal"] == "self_reported"
    # The apply link is on the employer's own domain, so it is handed over.
    assert row["apply_channel"] == ROSTER["postings"][0]["apply_url"]


def test_module_carries_no_em_dash_and_no_network_in_parse():
    src = pathlib.Path(sr.__file__).read_text(encoding="utf-8")
    assert "—" not in src
    # parse() is pure: the only httpx use is the inherited fetch() in base.
    assert "httpx" not in src.split("class SelfReportedClient")[1]
