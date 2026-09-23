"""Service-layer unit tests (in-memory DB) for the five MCP tools."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from openhire import service
from openhire.db import Application, Job, Watch
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
        assert r["remote_scope"] in {"worldwide", "region_locked", "country_locked", "unknown"}
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
        # What drove the average — so the number cannot be read as a verdict on its own.
        "median_days_open", "relisted_postings", "last_touched_reported_by_ats",
        # Employer-DECLARED, and only ever about the employer — never about a candidate.
        # The aggregate-only rule below still holds over the whole payload.
        "claimed", "claimed_at", "response_sla_days",
    }
    assert info["active_jobs"] == 3
    # `verified` stays gone as a name; `claimed` replaces it and is only true behind a real
    # claim — the v0.1 field was always false, which is a trust signal that can only mislead.
    assert "verified" not in info
    assert info["claimed"] is False and info["response_sla_days"] is None
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


def test_a_result_says_which_requested_skill_it_carries(session):
    """A reviewer searched `rust`, got ten rows all titled "Security Engineer" and filed a
    filter bug. The filter was right; the titles simply could not show why. A payload that
    reports match_quality without naming the hit asks the reader to trust a number over
    their own eyes."""
    rows = service.search_jobs(session, skills=["rust"], now=NOW)
    assert rows, "fixture should match something"
    for r in rows:
        assert "rust" in r["matched_skills"]


def test_match_quality_is_scored_against_what_the_ranker_used(session):
    """required_skills alone used to produce match_quality 1.0 on every row: job_posting
    was handed only `skills`, which was empty, and an empty request means "neutral".
    The number shown was not the number that ordered the list."""
    rows = service.search_jobs(session, required_skills=["rust"], now=NOW)
    assert rows
    for r in rows:
        assert r["matched_skills"] == ["rust"]
        assert r["match_quality"] == 1.0  # genuinely earned now, not the empty-request default

    # And a row matching one of two requested skills must not read as a perfect match.
    partial = service.search_jobs(session, skills=["rust", "cobol"], now=NOW)
    assert partial
    for r in partial:
        assert r["match_quality"] < 1.0
        assert r["matched_skills"] == ["rust"]


def test_the_first_watch_pull_says_it_is_a_baseline_not_an_increment(session):
    """Round 6: a reviewer noticed the first check_watches returns the whole standing
    backlog under a field called `new_matches`, with nothing but `since: null` to say so.
    The behaviour is right (nobody has seen any of it yet); the labelling was not."""
    w = service.watch_intent(session, "#a3f9", {"skills": ["rust"]}, now=NOW)

    first = service.check_watches(session, "#a3f9", now=NOW)
    r = first["results"][0]
    assert r["watch_id"] == w["watch_id"]
    assert r["since"] is None
    assert r["is_first_pull"] is True
    assert r["baseline"], "a first pull must explain that it is a backlog"

    later = service.check_watches(session, "#a3f9", now=NOW + dt.timedelta(days=1))
    r2 = later["results"][0]
    assert r2["is_first_pull"] is False
    assert r2["baseline"] is None
    assert r2["since"] is not None


def test_an_apply_url_on_an_unknown_host_is_reported_not_offered(session):
    """apply_channel is the one field that becomes an ACTION: `ohp apply` opens it in the
    user's browser, and the string arrived in an employer's ATS response. A host we do not
    recognise is surfaced, labelled, rather than handed over. It is not hidden either:
    dropping it silently would leave a caller unable to apply with no idea why."""
    job = session.execute(select(Job)).scalars().first()
    job.apply_channel = "https://totally-not-an-ats.example/apply"
    session.flush()

    rows = service.search_jobs(session, None, None, None, 50, now=NOW)
    hit = [r for r in rows if r["job_id"] == job.id]
    assert hit, "the row itself must still be returned"
    r = hit[0]
    assert r["apply_channel"] is None
    assert r["apply_channel_blocked"] == "https://totally-not-an-ats.example/apply"
    assert r["apply_channel_note"]


def test_a_normal_ats_url_is_untouched(session):
    rows = service.search_jobs(session, None, None, None, 50, now=NOW)
    assert rows
    for r in rows:
        assert r["apply_channel"], "fixture URLs are canonical ATS hosts"
        assert "apply_channel_blocked" not in r
