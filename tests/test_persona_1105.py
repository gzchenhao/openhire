"""Persona night 2026-11-05 (reports/141)."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from openhire import service
from openhire.ats.boards import BoardNotSupported, detect_board
from openhire.db.models import Base, Company, Job
from openhire.errors import OpenHireError
from openhire.pipeline.extract import seniority_from_title

NOW = dt.datetime(2026, 11, 5, 12, 0, tzinfo=dt.timezone.utc)


def _job(jid, title, desc, cid="acme"):
    when = NOW - dt.timedelta(days=5)
    return Job(id=f"{cid}:{jid}", company_id=cid, title=title, description_raw=desc, skills=["x"], remote_policy="onsite",
               location="上海", first_seen_at=when, verified_at=NOW, posted_at=when, source="ats_public_api",
               content_hash=f"h{jid}", ghost_score=0.0, apply_channel=f"https://jobs.lever.co/{cid}/{jid}")


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        s.add(Company(id="acme", name="Acme", ats_vendor="lever", ats_tenant="acme", last_crawled_at=NOW))
        s.add(Company(id="lixiang", name="理想汽车 Li Auto", ats_vendor="lixiang", ats_tenant="lixiang",
                      careers_url="https://www.lixiang.com/employ/social.html", last_crawled_at=NOW))
        s.add(_job("exp", "嵌入式软件开发工程师", "社会招聘。要求：2年以上嵌入式开发经验。"))
        s.add(_job("grad", "算法工程师", "负责算法研发。"))
        s.add(_job("pm", "Policy Program Manager, Safeguards", "Own the program."))
        s.commit()
        yield s


def test_moka_campus_link_without_site_number_says_what_is_missing():
    with pytest.raises(BoardNotSupported) as e:
        detect_board("https://app.mokahr.com/campus-recruitment/geekplus")
    assert "site number" in e.value.hint and "站点编号" in e.value.hint
    assert detect_board("https://app.mokahr.com/campus-recruitment/geekplus/123")[0] == "moka"


def test_tlm_is_a_manager():
    assert seniority_from_title("Staff TLM, Perception, Sensor Pipelines") == "manager"


def test_program_manager_is_not_flagged_as_unclear(db):
    rows = {r["job_id"]: r for r in service.search_jobs(db, now=NOW)}
    assert "manager_title_unclear" not in [c["code"] for c in rows["acme:pm"]["check_before_apply"]]


def test_junior_filter_drops_experienced_track_rows(db):
    titles = {r["title"] for r in service.search_jobs(db, seniority=["intern", "junior", "unknown"], now=NOW)}
    assert "算法工程师" in titles and "嵌入式软件开发工程师" not in titles


def test_entry_level_count_of_unstated_rows(db):
    total: dict = {}
    service.search_jobs(db, entry_level=True, now=NOW, total_out=total)
    assert total["matched"] == 0 and total["entry_level_unstated"] == 2


def test_empty_fingerprint_says_so(db):
    out = service.check_watches(db, "#never-registered-k2p7", now=NOW)
    assert out["watches"] == 0 and "指纹" in out["summary"]["zh"] and "copied exactly" in out["summary"]["en"]


def test_watch_without_level_asks_for_it(db):
    w = service.watch_intent(db, "#nolevel-k2p7x8q1", {"title": ["算法"]}, now=NOW)
    assert "manage_watch" in w["what_happens_next"]["zh"]


def test_first_pull_lists_ten_and_points_to_search(db):
    for i in range(14):
        db.add(_job(f"b{i}", f"Perception Engineer {i}", "x"))
    db.commit()
    service.watch_intent(db, "#page-k2p7x8q1", {"title": ["perception"]}, now=NOW)
    r = service.check_watches(db, "#page-k2p7x8q1", now=NOW)["results"][0]
    assert len(r["baseline_postings"]) == service.WATCH_PAGE and r["truncated"] is True
    assert "search_jobs" in r["truncation_note"]
    assert "requirements" in r["baseline_postings"][0] and "date_source" in r["baseline_postings"][0]


def test_read_board_on_an_indexed_first_party_site_points_to_search(db):
    with pytest.raises(OpenHireError) as e:
        service.read_board(db, url="https://www.lixiang.com/employ/social.html", now=NOW)
    assert "search_jobs(company=\"lixiang\")" in e.value.message
