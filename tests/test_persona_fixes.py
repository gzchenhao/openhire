"""Fixes from the Pony.ai perception-engineer persona test (reports/051, 2026-09-23).

Three job seekers used the server through its MCP tools only; a verifier reproduced every
friction. These tests pin the ones that were code, not coverage.
"""
from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from openhire import service
from openhire.db.models import Base, Company, Job
from openhire.errors import OpenHireError
from openhire.pipeline.ranking import expand_skill, match_quality

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 9, 23, tzinfo=UTC)


def mkjob(jid, company_id, title, skills, *, posted_days_ago, role_family=None,
          location="Beijing", remote="onsite", updated_days_ago=None):
    posted = NOW - dt.timedelta(days=posted_days_ago)
    updated = NOW - dt.timedelta(days=updated_days_ago) if updated_days_ago is not None else None
    return Job(
        id=f"{company_id}:{jid}", company_id=company_id, title=title,
        description_raw=title, skills=skills, remote_policy=remote,
        salary_min=None, salary_max=None, salary_currency=None, salary_inferred=False,
        location=location, posted_at=posted, updated_at=updated,
        first_seen_at=posted, verified_at=NOW, source="ats_public_api",
        apply_channel=f"https://app.mokahr.com/apply/{company_id}/1#/job/{jid}",
        content_hash=f"h{jid}", ghost_score=0.0, role_family=role_family,
    )


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        s.add(Company(id="minieye", name="佑驾创新 MINIEYE", ats_vendor="moka", ats_tenant="minieye",
                      careers_url="x", verified=False, last_crawled_at=NOW))
        s.add(Company(id="ubtrobot", name="优必选 UBTECH", ats_vendor="beisen", ats_tenant="ubtrobot",
                      careers_url="y", verified=False, last_crawled_at=NOW))
        # The exact shape the testers hit: an old, classified row and a new, unclassified one.
        s.add(mkjob("old", "ubtrobot", "融合定位算法工程师", ["bev", "slam"],
                    posted_days_ago=484, role_family="engineering"))
        s.add(mkjob("new", "minieye", "L4-感知算法工程师-BJ", ["perception", "occupancy-networks", "bev"],
                    posted_days_ago=14, role_family=None))
        s.add(mkjob("sales", "minieye", "售前技术经理", ["lidar", "perception"],
                    posted_days_ago=30, role_family="sales"))
        s.commit()
        yield s


# --- 1. freshness is the employer's clock, so a 14-day posting outranks a 484-day one ----
def test_fresh_posting_outranks_stale_one_at_equal_match(session):
    rows = service.search_jobs(session, skills=["bev"], now=NOW)
    assert [r["job_id"] for r in rows][:2] == ["minieye:new", "ubtrobot:old"]
    fresh, stale = rows[0]["freshness"], rows[1]["freshness"]
    assert fresh > 0.9 and stale == 0.0, (fresh, stale)


# --- 2. role_family=null is "not classified yet", never "not engineering" ------------------
def test_unclassified_rows_pass_a_role_family_filter(session):
    rows = service.search_jobs(session, skills=["bev"], role_family="engineering", now=NOW)
    ids = {r["job_id"] for r in rows}
    assert "minieye:new" in ids, "the 14-day unclassified posting was hidden"
    assert "ubtrobot:old" in ids
    # ...while a row KNOWN to be another family is still excluded.
    rows = service.search_jobs(session, skills=["perception"], role_family="engineering", now=NOW)
    assert "minieye:sales" not in {r["job_id"] for r in rows}


# --- 3. Chinese and variant spellings reach the same rows ------------------------------
def test_chinese_skill_words_match_english_tags(session):
    rows = service.search_jobs(session, skills=["感知"], now=NOW)
    assert {r["job_id"] for r in rows} == {"minieye:new", "minieye:sales"}
    rows = service.search_jobs(session, skills=["占用网络"], now=NOW)
    assert [r["job_id"] for r in rows] == ["minieye:new"]
    assert rows[0]["matched_skills"] == ["occupancy-networks"]


def test_match_quality_counts_an_alias_hit_as_a_hit():
    assert match_quality(["感知", "点云"], ["perception"]) == pytest.approx(0.5)
    assert "occupancy networks" in expand_skill("占用网络")
    assert expand_skill("BEV") >= {"bev"}


def test_half_matched_search_reports_the_dropped_word(session):
    unknown, suggestions = service.skill_diagnostics(session, ["bev", "量子计算"], None)
    assert unknown == ["量子计算"]
    unknown, _ = service.skill_diagnostics(session, ["感知"], None)
    assert unknown == [], "感知 is not unknown when the index tags perception"


# --- 4. remote_scope never claims worldwide on a US-only row ----------------------------
@pytest.mark.parametrize("location,expected", [
    ("Remote, U.S", ("country_locked", ["US"])),
    ("Remote - US, Ann Arbor, MI", ("country_locked", ["US"])),
    ("Remote, United States", ("country_locked", ["US"])),
    ("Remote", ("worldwide", [])),
    ("Remote - Ann Arbor, MI", ("unknown", [])),
])
def test_remote_scope_reads_us_spellings_and_admits_ignorance(location, expected):
    assert service.classify_remote("remote", location) == expected


def test_remote_scope_does_not_see_us_inside_other_words():
    assert service.classify_remote("remote", "Remote - Austin") == ("unknown", [])
    assert service.classify_remote("remote", "Remote, campus based") == ("unknown", [])


# --- 5. watches: unknown keys refused, company scoping real, truncation reported --------
def test_watch_refuses_unknown_filter_keys(session):
    with pytest.raises(OpenHireError) as e:
        service.watch_intent(session, "#t3st", {"skills": ["bev"], "location": "北京"}, now=NOW)
    assert e.value.code == "ERR_UNKNOWN_FILTER"
    assert "location" in e.value.message


def test_watch_can_be_scoped_to_one_employer(session):
    w = service.watch_intent(session, "#t3st", {"skills": ["bev"], "company": "佑驾"}, now=NOW)
    assert w["status"] == "active"
    out = service.check_watches(session, "#t3st", now=NOW)
    res = out["results"][0]
    assert {m["job_id"] for m in res["new_matches"]} == {"minieye:new"}
    assert res["total_matching"] == 1 and res["truncated"] is False


def test_watch_on_unknown_employer_is_refused_at_registration(session):
    with pytest.raises(OpenHireError) as e:
        service.watch_intent(session, "#t3st", {"skills": ["bev"], "company": "Momenta"}, now=NOW)
    assert e.value.code == "ERR_COMPANY_NOT_FOUND"


def test_first_pull_reports_the_whole_standing_set_size(session):
    for i in range(service.MAX_PAGE_SIZE + 5):
        session.add(mkjob(f"bulk{i}", "minieye", f"Algo {i}", ["pytorch"], posted_days_ago=i))
    session.commit()
    service.watch_intent(session, "#bulk", {"skills": ["pytorch"]}, now=NOW)
    res = service.check_watches(session, "#bulk", now=NOW)["results"][0]
    assert res["total_matching"] == service.MAX_PAGE_SIZE + 5
    assert res["truncated"] is True and res["truncation_note"]
    assert len(res["new_matches"]) == service.MAX_PAGE_SIZE
    # The best-ranked rows are the freshest, not an alphabetical slice.
    assert res["new_matches"][0]["job_id"] == "minieye:bulk0"


# --- 6. get_company_info takes what search_jobs takes ------------------------------------
def test_company_info_resolves_a_name(session):
    info = service.get_company_info(session, "佑驾")
    assert info["company_id"] == "minieye"
    with pytest.raises(OpenHireError) as e:
        service.get_company_info(session, "Nonexistent Robotics Co")
    assert e.value.code == "ERR_COMPANY_NOT_FOUND"
    # Momenta is no longer "not found": it is known and deliberately not indexed, and the
    # answer says so (tests/test_not_indexed.py pins the shape).
    known = service.get_company_info(session, "Momenta")
    assert known["indexed"] is False and known["company_id"] is None


# --- 7. refresh_index must survive being called from inside a running event loop --------
def test_refresh_index_tool_runs_inside_a_running_loop(monkeypatch):
    """FastMCP calls the sync tool from its loop thread; the crawler calls asyncio.run().
    Before 0.6.3 that combination raised on every call. Simulate exactly that."""
    import asyncio

    from openhire import mcp_server, service

    def fake_refresh(session, company):
        # What the real crawl does: spin its own loop. Illegal on a thread with a running one.
        return {"refreshed": True, "ran": asyncio.run(asyncio.sleep(0, result="in-thread")), "company": company}

    monkeypatch.setattr(service, "refresh_company_index", fake_refresh)
    monkeypatch.setattr(mcp_server, "_await_index", lambda: None)

    async def call_from_loop():
        return mcp_server.refresh_index("minieye")

    out = asyncio.run(call_from_loop())
    assert out == {"refreshed": True, "ran": "in-thread", "company": "minieye"}


# --- 8. the leftovers: location filter, limit=0, fingerprint reuse notice ------------------
def test_location_filter_is_a_caseless_substring_in_either_language(session):
    session.add(mkjob("sh", "minieye", "L4-感知算法工程师-SH", ["bev"], posted_days_ago=14, location="上海"))
    session.commit()
    ids = {r["job_id"] for r in service.search_jobs(session, skills=["bev"], location="上海", now=NOW)}
    assert ids == {"minieye:sh"}
    ids = {r["job_id"] for r in service.search_jobs(session, skills=["bev"], location="beijing", now=NOW)}
    assert ids == {"minieye:new", "ubtrobot:old"}


def test_limit_zero_is_an_error_not_one_row(session):
    with pytest.raises(OpenHireError) as e:
        service.search_jobs(session, skills=["bev"], limit=0, now=NOW)
    assert e.value.code == "ERR_BAD_PAGE"


def test_reusing_a_fingerprint_is_reported(session):
    first = service.watch_intent(session, "#p0ny", {"skills": ["bev"]}, now=NOW)
    assert first["existing_watches"] == 0
    second = service.watch_intent(session, "#p0ny", {"skills": ["slam"]}, now=NOW)
    assert second["existing_watches"] == 1
    assert "already had 1 active watch" in second["fingerprint_notice"]
