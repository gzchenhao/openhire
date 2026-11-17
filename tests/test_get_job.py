"""get_job (0.8.68, reports/148): the description the index holds, one posting at a time.

A product-manager persona asked whether a 理想 posting was really product work; the text was in
the index (check_employer said so) and no tool would hand it over (persona test, 2026-11-16).
"""
import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from openhire import service
from openhire.db.models import Base, Company, Job
from openhire.errors import OpenHireError

NOW = dt.datetime(2026, 11, 17, 12, 0, tzinfo=dt.timezone.utc)
DESC = "1. 负责座舱产品规划；\n2. 3年以上产品经理经验。" * 20


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        s.add(Company(id="lixiang", name="理想汽车", ats_vendor="lixiang", ats_tenant="x", last_crawled_at=NOW))

        def add(jid, desc, verified, delisted=None):
            s.add(Job(id=f"lixiang:{jid}", company_id="lixiang", title="座舱产品经理", description_raw=desc,
                      skills=["x"], remote_policy="onsite", location="上海", first_seen_at=NOW - dt.timedelta(days=20),
                      verified_at=verified, delisted_at=delisted, source="ats_public_api", content_hash=jid,
                      ghost_score=0.0, apply_channel=f"https://www.lixiang.com/employ/{jid}"))
        add("live", DESC, NOW)
        add("closed", "已下架的岗位描述", NOW - dt.timedelta(days=3), delisted=NOW - dt.timedelta(days=2))
        add("stale", "很久没核到", NOW - dt.timedelta(days=40))
        add("empty", "", NOW)
        s.commit()
        yield s


def test_returns_the_row_and_its_description(db):
    out = service.get_job(db, "lixiang:live", now=NOW)
    assert out["job_id"] == "lixiang:live" and out["status"] == "live"
    assert out["description"] == DESC[:8000] and out["description_total_chars"] == len(DESC)
    assert out["description_next_offset"] is None
    assert "apply_channel" in out and "dates_in_words" in out and "requirements" in out
    assert "rank_score" not in out and "match_quality" not in out, "no query, so no fit score"


def test_pages_a_long_description(db):
    first = service.get_job(db, "lixiang:live", now=NOW, max_chars=100)
    assert len(first["description"]) == 100 and first["description_next_offset"] == 100
    second = service.get_job(db, "lixiang:live", now=NOW, max_chars=100, offset=100)
    assert second["description"] == DESC[100:200]


def test_closed_and_stale_postings_say_so(db):
    closed = service.get_job(db, "lixiang:closed", now=NOW)
    assert closed["status"] == "closed" and "下架" in closed["status_in_words"]["zh"]
    stale = service.get_job(db, "lixiang:stale", now=NOW)
    assert stale["status"] == "not_verified_recently" and "refresh_index" in stale["status_in_words"]["en"]


def test_an_empty_description_is_not_invented(db):
    out = service.get_job(db, "lixiang:empty", now=NOW)
    assert out["description"] == "" and "do not write one" in out["description_note"]


def test_unknown_id_and_bad_page(db):
    with pytest.raises(OpenHireError) as e:
        service.get_job(db, "lixiang:nope", now=NOW)
    assert e.value.code == "ERR_JOB_NOT_FOUND"
    with pytest.raises(OpenHireError) as e:
        service.get_job(db, "lixiang:live", now=NOW, max_chars=0)
    assert e.value.code == "ERR_BAD_PAGE"


def test_refuses_personal_data_as_an_id(db):
    with pytest.raises(OpenHireError):
        service.get_job(db, "张三 13800000000 zhangsan@example.com", now=NOW)
