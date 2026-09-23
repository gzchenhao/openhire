"""Known-but-not-indexed employers: "not in the index, and here is why" is an answer.

Ten hot Chinese employers run their careers sites on Feishu Recruitment, whose job-list
API requires a client-computed request signature. We treat that as access control and do
not work around it (reports/014, reports/020). Before this, a search for Momenta got the
same generic "not indexed" hint as a typo and get_company_info raised
ERR_COMPANY_NOT_FOUND, so a seeker could not tell "not here yet" from "we know why".

Nothing in here touches the network: the registry is declarative and the service only
reads it after the live index came up empty.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import inspect
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from openhire import mcp_server, service
from openhire.db.models import Base, Company, Job
from openhire.errors import OpenHireError
from openhire.seed import not_indexed

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 9, 23, tzinfo=UTC)
EM_DASH = chr(0x2014)  # spelled as a code point so this file itself carries none


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        s.add(Company(id="minieye", name="佑驾创新 MINIEYE", ats_vendor="moka",
                      ats_tenant="minieye", careers_url="x", last_crawled_at=NOW))
        s.add(Job(
            id="minieye:1", company_id="minieye", title="感知算法工程师", description_raw="x",
            skills=["perception", "bev"], remote_policy="onsite", location="Beijing",
            posted_at=NOW, first_seen_at=NOW, verified_at=NOW, source="ats_public_api",
            apply_channel="https://app.mokahr.com/apply/minieye/1#/job/1", content_hash="h1",
            ghost_score=0.0, role_family="engineering",
        ))
        s.commit()
        yield s


# --- the registry itself ------------------------------------------------------------------
def test_registry_holds_the_ten_named_employers_with_honest_fields():
    ids = [e.id for e in not_indexed.NOT_INDEXED]
    assert ids == ["momenta", "ponyai", "agibot", "minimax", "zhipu", "sensetime", "limx",
                   "xsquare", "spiritai", "booster"]
    assert len(set(ids)) == len(ids)
    for e in not_indexed.NOT_INDEXED:
        assert e.ats == "feishu"
        assert e.aliases, e.id
        assert "request signature" in e.reason and "access control" in e.reason
        assert "do not work around it" in e.reason
        # A portal URL is either confirmed (https, employer's own host) or absent; never a guess.
        assert e.careers_url is None or e.careers_url.startswith("https://"), e.id
        assert e.employer_opt_in["scopes"] == ["hire:site:readonly", "hire:site_job_post:readonly"]
        assert "read-only" in e.employer_opt_in["what"]
        assert "never by payment" in e.employer_opt_in["how"]


def test_registry_urls_are_the_confirmed_ones_and_say_what_confirmed_them():
    """Each host was confirmed by one plain GET (2026-09-23); reports/014 showed a 200
    alone is not enough. Nine were confirmed by a <title> naming the employer. SenseTime
    was not: its title was never retrieved, and the entry says what the evidence is."""
    urls = {e.id: e.careers_url for e in not_indexed.NOT_INDEXED}
    assert urls["momenta"] == "https://momenta.jobs.feishu.cn/"
    assert urls["ponyai"] == "https://ponyai.jobs.feishu.cn/ponyai/"
    assert urls["agibot"] == "https://agirobot.jobs.feishu.cn/"
    assert urls["sensetime"] == "https://hr-jobs.sensetime.com/"
    assert urls["limx"] == "https://career.limxdynamics.com/"
    assert urls["minimax"] == "https://vrfi1sk8a0.jobs.feishu.cn/"
    assert urls["zhipu"] == "https://zhipu-ai.jobs.feishu.cn/"
    assert urls["xsquare"] == "https://x2-robot.jobs.feishu.cn/"
    assert urls["spiritai"] == "https://nwd4iy9rd2s.jobs.feishu.cn/"
    assert urls["booster"] == "https://booster.jobs.feishu.cn/"
    by_title = {e.id for e in not_indexed.NOT_INDEXED if e.confirmed_by == "title"}
    assert by_title == set(urls) - {"sensetime"}
    sensetime = not_indexed.by_id("sensetime")
    assert "feishucdn" in sensetime.confirmed_by and "title not retrieved" in sensetime.confirmed_by


def test_registry_does_no_network_and_carries_no_em_dash():
    src = Path(inspect.getsourcefile(not_indexed)).read_text(encoding="utf-8")
    for tok in ("httpx", "requests", "urllib", "aiohttp", "socket"):
        assert tok not in src, f"the registry must be declarative; found {tok!r}"
    assert EM_DASH not in src
    for e in not_indexed.NOT_INDEXED:
        assert EM_DASH not in e.reason and EM_DASH not in e.name
        for v in e.employer_opt_in.values():
            assert EM_DASH not in str(v)


@pytest.mark.parametrize("query,expected", [
    ("Momenta", "momenta"), ("momenta", "momenta"), ("魔门塔", "momenta"),
    ("Pony.ai", "ponyai"), ("小马智行", "ponyai"), ("小马", "ponyai"), ("PONY AI", "ponyai"),
    ("智元", "agibot"), ("AgiBot", "agibot"), ("agirobot", "agibot"),
    ("MiniMax", "minimax"), ("智谱", "zhipu"), ("Zhipu AI", "zhipu"),
    ("商汤", "sensetime"), ("SenseTime", "sensetime"),
    ("逐际动力", "limx"), ("LimX Dynamics", "limx"),
    ("自变量", "xsquare"), ("X Square", "xsquare"),
    ("千寻智能", "spiritai"), ("Spirit AI", "spiritai"),
    ("加速进化", "booster"), ("Booster Robotics", "booster"),
    ("momenta 招聘", "momenta"),          # an alias inside a longer question
])
def test_lookup_resolves_either_language(query, expected):
    hits = not_indexed.lookup(query)
    assert [e.id for e in hits] == [expected], query


def test_lookup_rejects_nothing_and_noise():
    assert not_indexed.lookup("") == []
    assert not_indexed.lookup("a") == []
    assert not_indexed.lookup("Nonexistent Robotics Co") == []
    assert not_indexed.lookup("佑驾") == []


@pytest.mark.parametrize("query", ["千寻位置", "小马拉车", "商汤湾"])
def test_a_two_character_short_form_inside_another_name_is_not_a_hit(query):
    """"千寻" and "小马" are exact aliases and still resolve on their own; inside a longer
    name they are somebody else ("千寻位置" is a positioning company), and answering
    "known, deliberately not indexed" for that would be a false claim about two employers."""
    assert not_indexed.lookup(query) == []


def test_company_info_for_a_look_alike_name_is_still_not_found(session):
    with pytest.raises(OpenHireError) as e:
        service.get_company_info(session, "千寻位置", now=NOW)
    assert e.value.code == "ERR_COMPANY_NOT_FOUND"


# --- search_jobs' empty-result diagnosis --------------------------------------------------
def test_empty_search_for_a_known_employer_says_why_and_where(session):
    d = service.diagnose_empty_search(session, company="Momenta", skills=["bev"])
    assert d["results"] == [] and d["matched"] == 0
    assert d["unknown_companies"] == ["Momenta"]
    assert d["suggestions"] == {}, "no 'did you mean' for an employer we know exactly"
    [k] = d["known_not_indexed"]
    assert k["id"] == "momenta" and k["indexed"] is False and k["ats"] == "feishu"
    assert k["careers_url"] == "https://momenta.jobs.feishu.cn/"
    assert "request signature" in k["reason"] and "access control" in k["reason"]
    assert k["employer_opt_in"]["scopes"] == ["hire:site:readonly", "hire:site_job_post:readonly"]
    # The hint is the sentence an agent will relay: portal, reason, and who can change it.
    assert "https://momenta.jobs.feishu.cn/" in d["hint"]
    assert "deliberately NOT in this index" in d["hint"]
    assert "not a typo" in d["hint"]
    assert "hire:site:readonly" in d["hint"]
    assert EM_DASH not in d["hint"]
    assert d["filters_applied"] == {"company": "Momenta", "skills": ["bev"]}


def test_empty_search_for_a_truly_unknown_employer_keeps_the_generic_hint(session):
    d = service.diagnose_empty_search(session, company="Nonexistent Robotics Co")
    assert "known_not_indexed" not in d
    assert "no company matching" in d["hint"]
    assert EM_DASH not in d["hint"]


def test_several_registry_matches_take_the_generic_hint_listing_them(session):
    """"robot" is inside AgiBot's, X Square's and Booster's aliases. The structured answer
    is about one employer (one portal, one reason), so with several it would silently be
    about the first; the generic hint lists the candidates instead and asks for one."""
    hits = [e.id for e in not_indexed.lookup("robot")]
    assert len(hits) > 1
    d = service.diagnose_empty_search(session, company="robot")
    assert d["results"] == [] and "known_not_indexed" not in d
    assert d["unknown_companies"] == ["robot"]
    listed = d["suggestions"]["robot"]
    assert len(listed) == len(hits)
    for name in listed:
        assert name in d["hint"]
    assert "Re-ask with one of them" in d["hint"]
    assert EM_DASH not in d["hint"]


def test_indexed_employer_wins_over_the_registry(session):
    # If Momenta ever authorises the scopes and gets indexed, the live index answers and
    # the registry is never consulted, even before the entry is removed.
    session.add(Company(id="momenta", name="Momenta 魔门塔", ats_vendor="feishu",
                        ats_tenant="momenta", careers_url="x", last_crawled_at=NOW))
    session.commit()
    d = service.diagnose_empty_search(session, company="Momenta", required_skills=["bev"])
    assert "known_not_indexed" not in d
    assert "is in the index" in d["hint"]


# --- get_company_info -----------------------------------------------------------------------
def test_company_info_is_a_structured_answer_not_an_error(session):
    for q in ("Momenta", "小马智行", "Pony.ai", "智谱", "booster"):
        info = service.get_company_info(session, q, now=NOW)
        assert info["indexed"] is False and info["company_id"] is None, q
        assert info["ats"] == "feishu" and info["careers_url"], q
        assert "request signature" in info["reason"] and "access control" in info["reason"]
        assert info["employer_opt_in"]["scopes"] == ["hire:site:readonly", "hire:site_job_post:readonly"]
        assert info["claimed"] is False
        assert "hint" in info and info["careers_url"] in info["hint"]
        # No trust signals: we hold none of their postings, and a zero would read as a verdict.
        for absent in ("ghost_score_avg", "active_jobs", "median_days_open", "relisted_postings"):
            assert absent not in info, (q, absent)
        assert EM_DASH not in info["hint"] and EM_DASH not in info["reason"]


def test_company_info_still_raises_for_a_truly_unknown_name(session):
    with pytest.raises(OpenHireError) as e:
        service.get_company_info(session, "Nonexistent Robotics Co", now=NOW)
    assert e.value.code == "ERR_COMPANY_NOT_FOUND"


def test_company_info_indexed_row_is_unchanged(session):
    info = service.get_company_info(session, "佑驾", now=NOW)
    assert info["company_id"] == "minieye" and "indexed" not in info


# --- watch_intent ---------------------------------------------------------------------------
def test_watch_on_a_known_not_indexed_employer_is_refused_with_the_reason(session):
    with pytest.raises(OpenHireError) as e:
        service.watch_intent(session, "#t3st-k2p7-x8q1", {"skills": ["bev"], "company": "Momenta"}, now=NOW)
    assert e.value.code == "ERR_COMPANY_NOT_FOUND"
    assert "request signature" in e.value.message
    assert "https://momenta.jobs.feishu.cn/" in e.value.message
    assert EM_DASH not in e.value.message


# --- the CLI ----------------------------------------------------------------------------------
def test_cli_prints_only_the_chinese_note_for_a_known_employer(monkeypatch):
    """The English hint is written for an agent; a person at the terminal gets the
    Chinese note with the portal, and nothing else about it."""
    from typer.testing import CliRunner

    from openhire.cli import app
    from openhire.db import init_db, session_scope

    init_db()
    with session_scope() as s:
        for t in (Job, Company):
            for row in s.execute(select(t)).scalars():
                s.delete(row)
        s.flush()
        s.add(Company(id="minieye", name="佑驾创新 MINIEYE", ats_vendor="moka",
                      ats_tenant="minieye", careers_url="x", last_crawled_at=NOW))
        # One live row, so this is a company miss and not the "no index yet" branch.
        s.add(Job(
            id="minieye:1", company_id="minieye", title="感知算法工程师", description_raw="x",
            skills=["perception", "bev"], remote_policy="onsite", location="Beijing",
            posted_at=NOW, first_seen_at=NOW, verified_at=NOW, source="ats_public_api",
            apply_channel="https://app.mokahr.com/apply/minieye/1#/job/1", content_hash="h1",
            ghost_score=0.0, role_family="engineering",
        ))
    res = CliRunner().invoke(app, ["search", "--skills", "bev", "--company", "Momenta"])
    assert res.exit_code == 0
    # The console wraps long lines, so compare with every whitespace character removed.
    out = "".join(res.stdout.split())
    assert "Momenta魔门塔未收录" in out
    assert "https://momenta.jobs.feishu.cn/" in out
    assert "deliberatelyNOTinthisindex" not in out
    assert "hire:site:readonly" not in out


# --- the MCP boundary -----------------------------------------------------------------------
def test_tool_docstrings_mention_the_known_not_indexed_answer():
    # Docstrings wrap at 90 columns, so compare with whitespace normalised.
    search_doc = " ".join((mcp_server.search_jobs.__doc__ or "").split())
    info_doc = " ".join((mcp_server.get_company_info.__doc__ or "").split())
    assert "known_not_indexed" in search_doc
    assert "hire:site:readonly" in search_doc and "hire:site_job_post:readonly" in search_doc
    assert "Momenta" in search_doc and "Momenta" in info_doc
    assert "request signature" in search_doc and "request signature" in info_doc
    assert "access control" in info_doc and "employer_opt_in" in info_doc
    # The registered tool descriptions are what the agent actually reads: list them the
    # way a client does (tests/test_privacy.py and test_mcp_acceptance.py do the same).
    from mcp.shared.memory import create_connected_server_and_client_session as connect

    async def _described():
        async with connect(mcp_server.mcp) as client:
            return {t.name: t.description or "" for t in (await client.list_tools()).tools}

    described = asyncio.run(_described())
    assert "known_not_indexed" in described["search_jobs"]
    assert "hire:site_job_post:readonly" in described["get_company_info"]


def test_new_user_facing_strings_carry_no_em_dash():
    src = Path(inspect.getsourcefile(service)).read_text(encoding="utf-8")
    for fn in ("known_not_indexed_hint", "known_not_indexed_info"):
        body = inspect.getsource(getattr(service, fn))
        assert EM_DASH not in body, fn
    assert EM_DASH not in (mcp_server.get_company_info.__doc__ or "")
    assert src.count("known_not_indexed") >= 3
