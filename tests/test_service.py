"""Service-layer unit tests (in-memory DB) for the five MCP tools."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from openhire import service
from openhire.db import Application, Watch
from openhire.db.models import Base, Company, Job
from openhire.errors import OpenHireError

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 7, 9, tzinfo=UTC)


def mkjob(jid, company_id, title, skills, remote, salary=None, first_seen=NOW, verified=NOW):
    smin, smax, cur = (salary if salary else (None, None, None))
    return Job(
        id=f"{company_id}:{jid}", company_id=company_id, title=title,
        description_raw=title, skills=skills, remote_policy=remote,
        salary_min=smin, salary_max=smax, salary_currency=cur, salary_inferred=False,
        location="Remote" if remote == "remote" else "NYC",
        first_seen_at=first_seen, verified_at=verified, source="ats_public_api",
        apply_channel=f"https://boards.greenhouse.io/embed/job_app?for={company_id}&token={jid}",
        content_hash=f"h{jid}", ghost_score=0.0,
    )


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        s.add(Company(id="acme", name="Acme AI", ats_vendor="greenhouse", ats_tenant="acme",
                      careers_url="x", verified=False, last_crawled_at=NOW))
        s.add(Company(id="beta", name="Beta Labs", ats_vendor="lever", ats_tenant="beta",
                      careers_url="y", verified=True, last_crawled_at=NOW))
        s.add(mkjob("1", "acme", "LLM Platform Engineer", ["rust", "k8s", "rag"], "remote"))
        s.add(mkjob("2", "acme", "Java Backend (onsite)", ["java", "sql"], "onsite"))
        s.add(mkjob("3", "acme", "Go Infra Engineer", ["go", "k8s"], "remote",
                    salary=(200000, 260000, "USD")))
        s.add(mkjob("4", "beta", "Senior Rust Engineer", ["rust"], "remote",
                    salary=(650000, 800000, "USD")))
        s.commit()
        yield s


# --- search_jobs --------------------------------------------------------------
def test_search_hard_filters_remote_and_skills(session):
    res = service.search_jobs(session, skills=["rust", "k8s"], remote=True, now=NOW)
    ids = {r["job_id"] for r in res}
    assert "acme:1" in ids  # rust+k8s remote
    assert "acme:3" in ids  # k8s remote
    assert "beta:4" in ids  # rust remote
    assert "acme:2" not in ids  # onsite → filtered out


def test_every_result_has_five_protocol_fields(session):
    res = service.search_jobs(session, skills=["rust"], remote=True, now=NOW)
    assert res
    for r in res:
        assert r["verified_at"] and r["source"] == "ats_public_api"
        assert r["ghost_score"] is not None
        assert r["response_sla_days"] is None  # v0.1
        assert r["apply_channel"].startswith("https://")


def test_search_remote_results_are_actually_remote(session):
    res = service.search_jobs(session, skills=["rust", "k8s"], remote=True, now=NOW)
    assert all(r["remote_policy"] == "remote" for r in res)


def test_min_salary_keeps_unstated_by_default(session):
    # New semantics: a floor keeps roles with NO stated pay (they can't be ruled out);
    # only the stated role BELOW the floor (acme:3, 200–260k) is dropped.
    res = service.search_jobs(session, min_salary=600000, now=NOW)
    ids = {r["job_id"] for r in res}
    assert "beta:4" in ids           # 650–800k clears the floor
    assert "acme:3" not in ids       # 200–260k stated, below floor → dropped
    assert {"acme:1", "acme:2"} <= ids  # unstated pay is kept


def test_require_stated_salary_drops_unstated(session):
    res = service.search_jobs(session, min_salary=600000, require_stated_salary=True, now=NOW)
    ids = {r["job_id"] for r in res}
    assert ids == {"beta:4"}  # only the stated role clearing the floor survives


def test_currency_filter_implies_stated_pay(session):
    res = service.search_jobs(session, currency="usd", now=NOW)
    ids = {r["job_id"] for r in res}
    assert ids == {"acme:3", "beta:4"}  # the two USD-stated roles; unstated excluded


def test_required_skills_is_and_semantics(session):
    # ANY-overlap would match acme:3/beta:4 too; AND requires BOTH rust and k8s → acme:1.
    res = service.search_jobs(session, required_skills=["rust", "k8s"], now=NOW)
    assert {r["job_id"] for r in res} == {"acme:1"}


def test_remote_scope_and_regions_exposed(session):
    res = service.search_jobs(session, skills=["rust"], remote=True, now=NOW)
    for r in res:
        assert r["remote_scope"] in {"worldwide", "region_locked", "country_locked"}
        assert isinstance(r["eligible_regions"], list)
        assert "days_open" in r and "datePosted" in r and "role_family" in r


def test_ranking_prefers_higher_match(session):
    # rust+k8s: acme:1 matches both (1.0), acme:3 & beta:4 match one (0.5) → acme:1 first.
    res = service.search_jobs(session, skills=["rust", "k8s"], remote=True, now=NOW)
    assert res[0]["job_id"] == "acme:1"
    assert res[0]["match_quality"] == pytest.approx(1.0)


# --- get_company_info ---------------------------------------------------------
def test_company_info_aggregate_only(session):
    info = service.get_company_info(session, "acme", now=NOW)
    assert set(info) == {
        "company_id", "company", "ghost_score_avg", "active_jobs", "index_built_at",
    }
    assert info["active_jobs"] == 3
    assert "verified" not in info  # removed: it was always false (a false trust signal)
    # No individual candidate data may appear anywhere in the payload.
    blob = str(info).lower()
    for tok in ("fingerprint", "email", "resume", "applicant", "candidate", "receipt"):
        assert tok not in blob


def test_company_info_not_found(session):
    with pytest.raises(OpenHireError) as e:
        service.get_company_info(session, "nope", now=NOW)
    assert e.value.code == "ERR_COMPANY_NOT_FOUND"


# --- watch_intent -------------------------------------------------------------
def test_watch_intent_returns_id_and_stores_only_anon(session):
    out = service.watch_intent(session, "#a3f9", {"skills": ["rust"], "remote": True}, now=NOW)
    assert out["status"] == "active" and out["watch_id"].startswith("w_")
    w = session.execute(select(Watch)).scalars().one()
    assert w.fingerprint == "#a3f9"
    assert w.filters == {"skills": ["rust"], "remote": True}


def test_watch_stores_required_skills_and_role_family(session):
    out = service.watch_intent(
        session, "#a3f9",
        {"required_skills": ["Rust", "K8S"], "role_family": "Engineering", "remote": True},
        now=NOW,
    )
    w = session.execute(select(Watch)).scalars().one()
    assert w.filters["required_skills"] == ["rust", "k8s"]  # normalized
    assert w.filters["role_family"] == "engineering"
    assert out["status"] == "active"


def test_check_watches_applies_required_skills_and_role_family(session):
    # A sales role that shares a skill would slip through ANY-overlap; required_skills (AND)
    # + role_family keep the watch's matches clean.
    session.add(mkjob("s1", "acme", "Sales Engineer", ["rust"], "remote"))
    session.flush()
    session.execute(
        select(Job).where(Job.id == "acme:s1")
    ).scalars().one().role_family = "sales"
    session.execute(select(Job).where(Job.id == "acme:1")).scalars().one().role_family = "engineering"
    session.flush()

    service.watch_intent(
        session, "#eng",
        {"required_skills": ["rust", "k8s"], "role_family": "engineering", "remote": True},
        now=NOW,
    )
    res = service.check_watches(session, "#eng", now=NOW + dt.timedelta(hours=1))
    ids = {m["job_id"] for r in res["results"] for m in r["new_matches"]}
    assert "acme:1" in ids       # rust+k8s engineering
    assert "acme:s1" not in ids  # sales, and lacks k8s → excluded


def test_watch_intent_rejects_pii_in_filters(session):
    with pytest.raises(OpenHireError) as e:
        service.watch_intent(session, "#a3f9", {"skills": ["rust"], "email": "a@b.c"}, now=NOW)
    assert e.value.code == "ERR_PII_NOT_ACCEPTED"


# --- check_watches ------------------------------------------------------------
def test_check_watches_returns_increment(session):
    service.watch_intent(session, "#a3f9", {"skills": ["rust"], "remote": True}, now=NOW)
    # First pull sees existing matches and advances the marker.
    first = service.check_watches(session, "#a3f9", now=NOW + dt.timedelta(hours=1))
    assert first["new_matches"] >= 1

    # A brand-new matching job appears later.
    later = NOW + dt.timedelta(days=1)
    session.add(mkjob("9", "beta", "Staff Rust Engineer", ["rust"], "remote",
                      first_seen=later, verified=later))
    session.flush()

    second = service.check_watches(session, "#a3f9", now=later + dt.timedelta(hours=1))
    new_ids = {m["job_id"] for r in second["results"] for m in r["new_matches"]}
    assert "beta:9" in new_ids  # only the increment
    assert "acme:1" not in new_ids  # already notified earlier


def test_check_watches_empty_after_no_new(session):
    service.watch_intent(session, "#zzz", {"skills": ["rust"], "remote": True}, now=NOW)
    service.check_watches(session, "#zzz", now=NOW + dt.timedelta(hours=1))
    again = service.check_watches(session, "#zzz", now=NOW + dt.timedelta(hours=2))
    assert again["new_matches"] == 0


# --- apply --------------------------------------------------------------------
def test_apply_authorized_records_receipt_no_resume(session):
    out = service.apply(session, "acme:1", "#a3f9", True, now=NOW)
    assert out["resume_transmitted"] is False
    assert out["delivered_via"] == "employer_site"
    assert out["receipt_id"].startswith("r_")
    assert out["apply_channel"].startswith("https://")
    app = session.get(Application, out["receipt_id"])
    assert app.authorized is True and app.fingerprint == "#a3f9"


def test_apply_requires_authorization(session):
    with pytest.raises(OpenHireError) as e:
        service.apply(session, "acme:1", "#a3f9", False, now=NOW)
    assert e.value.code == "ERR_NOT_AUTHORIZED"


def test_apply_unknown_job(session):
    with pytest.raises(OpenHireError) as e:
        service.apply(session, "acme:404", "#a3f9", True, now=NOW)
    assert e.value.code == "ERR_JOB_NOT_FOUND"


def test_apply_rejects_resume_payload(session):
    with pytest.raises(OpenHireError) as e:
        service.apply(session, "acme:1", "#a3f9", True, now=NOW,
                      extra_arguments={"resume": "John Doe, 10y experience..."})
    assert e.value.code == "ERR_RESUME_NEVER_TRANSMITTED"


def test_apply_rejects_resume_crammed_into_fingerprint(session):
    resume = "Name: John Doe\nEmail: john@x.com\n" + "experience " * 50
    with pytest.raises(OpenHireError) as e:
        service.apply(session, "acme:1", resume, True, now=NOW)
    assert e.value.code == "ERR_RESUME_NEVER_TRANSMITTED"
