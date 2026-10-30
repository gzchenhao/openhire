"""Sector filter (reports/109): four of ten simulated seekers on 2026-10-30 asked for
"autonomous-driving companies only" and the assistant had to search employer by employer."""

from __future__ import annotations

import datetime as dt

import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from openhire import service
from openhire.db.models import Base
from openhire.errors import OpenHireError
from openhire.seed import not_indexed, sectors
from openhire.seed.candidates import all_candidates


def test_every_seeded_employer_has_exactly_one_sector():
    slugs = {c.slug for c in all_candidates()}
    labelled = [cid for ids in sectors._BY_SECTOR.values() for cid in ids]
    assert len(labelled) == len(set(labelled)), "an employer is listed under two sectors"
    assert slugs == set(labelled), f"unlabelled: {sorted(slugs - set(labelled))}; stale: {sorted(set(labelled) - slugs)}"


def test_sector_words_match_the_portal_directory_and_both_languages():
    assert set(not_indexed.SECTORS) <= set(sectors.SECTORS)
    for word, want in [("智驾", "autonomous_driving"), ("Self-Driving", "autonomous_driving"), ("机器人", "embodied_ai"),
                       ("具身", "embodied_ai"), ("大模型", "ai_infra"), ("其他", "other"), ("ai_infra", "ai_infra")]:
        assert service.check_sector(word) == want, word
    assert service.check_sector(None) is None and service.check_sector("") is None
    with pytest.raises(OpenHireError) as e:
        service.check_sector("robtics")
    assert e.value.code == "ERR_UNKNOWN_SECTOR"


def test_known_labels_spot_check():
    assert sectors.sector_of("waymo") == "autonomous_driving" and sectors.sector_of("unitree") == "embodied_ai"
    assert sectors.sector_of("anthropic") == "ai_infra" and sectors.sector_of("figma") == "other"
    assert sectors.sector_of("my-own-board") is None


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        yield s


def test_search_and_watch_filter_by_sector(session):
    from openhire.db.models import Company, Job
    now = dt.datetime(2026, 10, 30, tzinfo=dt.timezone.utc)
    for cid, title in (("waymo", "Perception Engineer"), ("unitree", "运动控制工程师"), ("figma", "Product Designer")):
        session.add(Company(id=cid, name=cid, ats_vendor="greenhouse", ats_tenant=cid))
        session.add(Job(id=f"{cid}:1", company_id=cid, title=title, description_raw=title, source="ats_public_api",
                        first_seen_at=now, verified_at=now, posted_at=now, skills=[], location="X",
                        content_hash=f"h{cid}", ghost_score=0.0, remote_policy="onsite",
                        apply_channel=f"https://boards.greenhouse.io/{cid}/jobs/1"))
    session.flush()
    rows = service.search_jobs(session, sector="智驾", now=now)
    assert [r["company_id"] for r in rows] == ["waymo"] and rows[0]["sector"] == "autonomous_driving"
    assert [r["company_id"] for r in service.search_jobs(session, sector="embodied_ai", now=now)] == ["unitree"]
    w = service.watch_intent(session, "#sector-k2p7x8q1", {"sector": "机器人"}, now=now)
    assert w["matching_now"] == 1
    out = service.diagnose_empty_search(session, sector="ai_infra", title=["nothing-like-this"])
    assert out["filters_applied"]["sector"] == "ai_infra"
