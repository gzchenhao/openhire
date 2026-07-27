"""salary_period — monthly (CN) vs annual (Western) pay must stay comparable.

Chinese portals publish 月薪 ("25K-50K 元/月"), Western boards publish annual. Both land
in the same salary_min/max columns, so before v0.2 a 25,000 CNY/month role was compared
raw against an annual `--min-salary` floor and was silently dropped — every Chinese job
looked underpaid. Comparisons now annualise; the STORED figures stay exactly as the
employer published them.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from openhire import service
from openhire.ats.base import JobRecord
from openhire.ats.beisen import BeisenClient
from openhire.db.models import Base, Company, Job

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 7, 27, tzinfo=UTC)

# The real shape of the acceptance case: 宇树 高级研发项目经理, 25K-50K 元/月.
CN_MIN, CN_MAX = 25000, 50000


def mkjob(jid, company_id, title, salary=None, period="annual"):
    smin, smax, cur = salary if salary else (None, None, None)
    return Job(
        id=f"{company_id}:{jid}", company_id=company_id, title=title,
        description_raw=title, skills=["python"], remote_policy="unknown",
        salary_min=smin, salary_max=smax, salary_currency=cur,
        salary_period=period, salary_inferred=False, location="杭州",
        first_seen_at=NOW, verified_at=NOW, source="ats_public_api",
        apply_channel=f"https://unitree.zhiye.com/social/detail?jobAdId={jid}",
        content_hash=f"h{jid}", ghost_score=0.0, role_family="engineering",
    )


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        s.add(Company(id="unitree", name="宇树科技 Unitree", ats_vendor="beisen",
                      ats_tenant="unitree", careers_url="x", last_crawled_at=NOW))
        s.add(Company(id="acme", name="Acme AI", ats_vendor="greenhouse",
                      ats_tenant="acme", careers_url="y", last_crawled_at=NOW))
        # 25K-50K 元/月 → 300,000–600,000 CNY once annualised.
        s.add(mkjob("cn1", "unitree", "高级研发项目经理",
                    salary=(CN_MIN, CN_MAX, "CNY"), period="monthly"))
        # A US role, published annually.
        s.add(mkjob("us1", "acme", "Staff Engineer",
                    salary=(200000, 260000, "USD"), period="annual"))
        # Unstated pay — must survive any floor (it cannot be ruled out).
        s.add(mkjob("us2", "acme", "Engineer, pay undisclosed"))
        s.commit()
        yield s


def ids(rows):
    return {r["job_id"] for r in rows}


# --- the regression this column exists for ------------------------------------
def test_monthly_job_survives_an_annual_floor_it_actually_clears(session):
    """25K-50K/月 = 300k-600k CNY a year, so a 300,000 floor must NOT drop it.

    Before salary_period this compared 50000 >= 300000 → False → dropped.
    """
    assert "unitree:cn1" in ids(service.search_jobs(session, min_salary=300000, now=NOW))


@pytest.mark.parametrize(
    "floor,kept",
    [
        (100000, True),   # far below annualised min
        (300000, True),   # exactly the annualised MIN — boundary, inclusive
        (600000, True),   # exactly the annualised MAX — boundary, inclusive
        (600001, False),  # just past the top of the range
        (900000, False),  # far above
    ],
)
def test_annual_floor_boundaries_for_a_monthly_job(session, floor, kept):
    assert ("unitree:cn1" in ids(service.search_jobs(session, min_salary=floor, now=NOW))) is kept


def test_annual_job_is_not_multiplied(session):
    """An annual role must never be inflated ×12 — 260k stays 260k."""
    assert "acme:us1" in ids(service.search_jobs(session, min_salary=260000, now=NOW))
    assert "acme:us1" not in ids(service.search_jobs(session, min_salary=260001, now=NOW))


def test_unstated_pay_still_survives_a_floor(session):
    assert "acme:us2" in ids(service.search_jobs(session, min_salary=900000, now=NOW))


# --- storage is never rewritten ------------------------------------------------
def test_stored_figures_stay_as_published(session):
    job = session.get(Job, "unitree:cn1")
    assert (job.salary_min, job.salary_max) == (CN_MIN, CN_MAX)
    assert job.salary_period == "monthly"
    row = [r for r in service.search_jobs(session, now=NOW, limit=50)
           if r["job_id"] == "unitree:cn1"][0]
    assert (row["salary_min"], row["salary_max"]) == (CN_MIN, CN_MAX)
    assert row["salary_period"] == "monthly"


def test_job_posting_always_reports_a_period(session):
    rows = service.search_jobs(session, now=NOW, limit=50)
    assert {r["salary_period"] for r in rows} == {"monthly", "annual"}


def test_null_period_is_treated_as_annual(session):
    """Rows predating the migration have NULL; they are Western-ATS annual figures."""
    session.add(mkjob("legacy", "acme", "Legacy row", salary=(400000, 500000, "USD")))
    session.query(Job).filter(Job.id == "acme:legacy").update({"salary_period": None})
    session.commit()
    assert "acme:legacy" in ids(service.search_jobs(session, min_salary=400000, now=NOW))
    # Not annualised: 500000×12 would clear this floor, a NULL-as-monthly bug.
    assert "acme:legacy" not in ids(service.search_jobs(session, min_salary=600000, now=NOW))
    row = [r for r in service.search_jobs(session, now=NOW, limit=50)
           if r["job_id"] == "acme:legacy"][0]
    assert row["salary_period"] == "annual"


# --- helper + adapter wiring ---------------------------------------------------
@pytest.mark.parametrize(
    "value,period,expected",
    [(25000, "monthly", 300000), (25000, "annual", 25000),
     (25000, None, 25000), (None, "monthly", None)],
)
def test_annualise_helper(value, period, expected):
    assert service.annualise(value, period) == expected


def test_beisen_records_are_monthly():
    payload = {"Data": [{"Id": "g1", "JobAdName": "算法工程师", "Duty": "d", "Require": "r",
                         "Salary": "25K-50K 元/月", "LocNames": ["浙江省·杭州市"]}]}
    rec = BeisenClient().parse(payload, "unitree")[0]
    assert rec.salary_period == "monthly"
    assert (rec.salary_min, rec.salary_max, rec.salary_currency) == (25000, 50000, "CNY")


def test_western_records_default_to_annual():
    assert JobRecord(ats_job_id="1", title="t", description_raw="d",
                     apply_channel="https://x").salary_period == "annual"
