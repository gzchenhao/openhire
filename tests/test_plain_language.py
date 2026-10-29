"""The fields written for the person reading the answer (0.8.30, reports/100): dates as a
sentence, where the date comes from, what to confirm before applying, what a watch does
next, what a check_watches pull is, and which kind of "nothing" an empty search is."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from openhire import service
from openhire.db.models import Base, Company, Job

NOW = dt.datetime(2026, 10, 28, 12, 0, tzinfo=dt.timezone.utc)
FORBIDDEN = ("假岗", "僵尸", "不招了", "fake", "ghost", "zombie", "dead")


def _job(jid, cid, title, *, posted_days=None, seen_days=10, salary=None, remote=None, apply=None):
    seen = NOW - dt.timedelta(days=seen_days)
    posted = NOW - dt.timedelta(days=posted_days) if posted_days is not None else None
    smin, smax, cur = salary or (None, None, None)
    return Job(id=f"{cid}:{jid}", company_id=cid, title=title, description_raw=title, skills=["perception"],
               remote_policy=remote or "onsite", location="Remote - somewhere" if remote else "Shanghai",
               first_seen_at=seen, verified_at=NOW, posted_at=posted, salary_min=smin, salary_max=smax,
               salary_currency=cur, source="ats_public_api", content_hash=f"h{jid}", ghost_score=0.0,
               apply_channel=apply or f"https://jobs.lever.co/{cid}/{jid}")


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        s.add(Company(id="acme", name="Acme", ats_vendor="lever", ats_tenant="acme", last_crawled_at=NOW))
        s.add(Company(id="lixiang", name="理想汽车 Li Auto", ats_vendor="lixiang", ats_tenant="lixiang", last_crawled_at=NOW))
        s.add(Company(id="roster", name="Roster Co", ats_vendor="self_reported", ats_tenant="roster", last_crawled_at=NOW))
        s.add(_job(1, "acme", "Perception Engineer", posted_days=35, salary=(150000, 200000, "USD")))
        s.add(_job(2, "acme", "Old Perception Engineer", posted_days=120))
        s.add(_job(3, "lixiang", "感知算法工程师", posted_days=None, seen_days=40))
        s.add(_job(4, "roster", "Perception Engineer", posted_days=3, apply="https://evil.example/apply"))
        s.add(_job(5, "acme", "Remote Perception Engineer", posted_days=7, remote="remote"))
        s.commit()
        yield s


def _row(db, job_id):
    rows = service.search_jobs(db, title=["perception", "感知"], limit=50, now=NOW)
    return next(r for r in rows if r["job_id"] == job_id)


def test_employer_date_row_reads_as_a_sentence(db):
    r = _row(db, "acme:1")
    assert r["date_source"] == "employer_ats"
    zh, en = r["dates_in_words"]["zh"], r["dates_in_words"]["en"]
    assert zh == "雇主发布日期 2026-09-23，在架 35 天；最近核验 2026-10-28，雇主系统当天仍返回这条岗位。"
    assert en.startswith("Employer posting date 2026-09-23, open 35 days; last verified 2026-10-28")
    assert r["check_before_apply"] == []            # nothing stood out: dated, paid, onsite, trusted link


def test_no_employer_date_says_first_seen_and_a_lower_bound(db):
    r = _row(db, "lixiang:3")
    assert r["date_source"] == "index_first_seen" and r["date_signal"] == "not_reported_by_ats"
    zh = r["dates_in_words"]["zh"]
    assert "雇主系统没有提供发布日期" in zh and "本工具首次发现日期 2026-09-18" in zh and "在架至少 40 天" in zh
    assert "at least 40 days" in r["dates_in_words"]["en"]
    codes = [c["code"] for c in r["check_before_apply"]]
    assert codes == ["no_employer_date", "salary_not_stated"]


def test_long_open_rows_get_the_confirm_first_line_and_nothing_stronger(db):
    r = _row(db, "acme:2")
    assert r["days_open"] == 120
    assert "在架较久，投递前建议先确认仍在招" in r["dates_in_words"]["zh"]
    assert "worth confirming it is still being filled" in r["dates_in_words"]["en"]
    assert [c["code"] for c in r["check_before_apply"]] == ["open_over_90d", "salary_not_stated"]
    blob = (r["dates_in_words"]["zh"] + r["dates_in_words"]["en"] + str(r["check_before_apply"])).lower()
    assert not any(w in blob for w in FORBIDDEN)


def test_self_reported_date_and_unrecognised_apply_host_are_named(db):
    r = _row(db, "roster:4")
    assert r["date_source"] == "employer_self_reported"
    assert "雇主自报发布日期" in r["dates_in_words"]["zh"]
    codes = [c["code"] for c in r["check_before_apply"]]
    assert "self_reported_date" in codes and "apply_link_unrecognised" in codes
    assert r["apply_channel"] is None


def test_remote_with_unknown_scope_is_flagged(db):
    r = _row(db, "acme:5")
    assert r["remote_scope"] == "unknown"
    assert "remote_scope_unknown" in [c["code"] for c in r["check_before_apply"]]


def test_each_item_carries_both_languages_and_a_code():
    items = service.check_before_apply(date_source="index_first_seen", days_open=200, salary_stated=False,
                                       remote_scope="unknown", apply_ok=False,
                                       correction={"status": "closed", "date_semantics": "requisition_created"})
    assert [i["code"] for i in items] == ["no_employer_date", "open_over_90d", "salary_not_stated", "remote_scope_unknown",
                                          "apply_link_unrecognised", "employer_says_closed", "date_is_requisition_created"]
    assert all(i["zh"] and i["en"] for i in items)
    words = service.dates_in_words(dt.date(2026, 1, 1), 300, "employer_ats", dt.date(2026, 10, 28),
                                   {"date_semantics": "requisition_created"})
    assert "内部立项日" in words["zh"] and "requisition" in words["en"]
    assert service.dates_in_words(None, None, "employer_ats", None)["zh"] == "这条岗位没有可用的日期。"


def test_watch_says_what_happens_next_and_counts_todays_matches(db):
    w = service.watch_intent(db, "#plain-k2p7x8q1", {"title": ["perception"]}, now=NOW)
    assert w["matching_now"] == 4
    zh = w["what_happens_next"]["zh"]
    assert "现在匹配 4 条，都是已有岗位，不是新发" in zh and "不会主动推送" in zh and "radar_check" in zh
    assert "does not push" in w["what_happens_next"]["en"]
    first = service.check_watches(db, "#plain-k2p7x8q1", now=NOW)
    r = first["results"][0]
    assert r["is_first_pull"] is True
    assert r["summary"]["zh"].startswith("首次检查：当前匹配 4 条") and "不是新发" in r["summary"]["zh"]
    assert first["summary"]["zh"].startswith("1 个雷达。首次检查")
    later = service.check_watches(db, "#plain-k2p7x8q1", now=NOW + dt.timedelta(days=1))
    assert later["results"][0]["summary"]["zh"].startswith("自 2026-10-28 以来没有新岗位")
    assert later["summary"]["en"] == "1 watch(es). Nothing new."


def test_board_watch_explains_the_live_read(db):
    w = service.watch_intent(db, "#plain-board-k2p7", {"board_url": "https://jobs.lever.co/okx"}, now=NOW)
    assert w["matching_now"] is None and "现读" in w["what_happens_next"]["zh"]


def test_an_empty_search_says_which_kind_of_nothing(db):
    miss = service.diagnose_empty_search(db, skills=["perception"], required_skills=["cobol"])
    assert miss["status"] == "unknown_tag" and miss["headline"]["zh"].startswith("没有匹配的岗位：条件里有索引认不出的词")
    genuine = service.diagnose_empty_search(db, skills=["perception"], role_family="hr")
    assert genuine["status"] == "no_match" and "放宽一项再搜" in genuine["headline"]["zh"]
    company = service.diagnose_empty_search(db, company="Nonesuch Robotics")
    assert company["status"] == "unknown_company" and company["headline"]["en"].startswith("No match: this employer")
    known = service.diagnose_empty_search(db, company="Momenta")
    assert known["status"] == "known_not_indexed" and "招聘门户" in known["headline"]["zh"]


def test_empty_index_headline():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        out = service.diagnose_empty_search(s, skills=["x"])
    assert out["status"] == "index_empty" and out["index_empty"] is True
    assert out["headline"]["zh"] == "本机还没有岗位数据，不是没有匹配的岗位。"


def test_persona_round_2026_10_29_fixes(db):
    """The first nightly persona run (reports/106): a first-seen age is a floor in ghost_reason
    too; the scheduled reminder names the tool that exists; a long fingerprint's earlier
    watches are the caller's own, not a collision."""
    r = _row(db, "lixiang:3")
    assert r["ghost_reason"].endswith("(at least: counted from the day OpenHire first saw it; the employer's system gives no date)")
    w = service.watch_intent(db, "#persona-k2p7x8q1", {"title": ["perception"]}, now=NOW)
    assert "check_watches" in w["what_happens_next"]["zh"] and "check_watches" in w["what_happens_next"]["en"]
    again = service.watch_intent(db, "#persona-k2p7x8q1", {"title": ["slam"]}, now=NOW)
    assert "most likely your own" in again["fingerprint_notice"]
    assert "another client chose" not in again["fingerprint_notice"]
