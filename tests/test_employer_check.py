"""`check_employer`: a checklist of facts with sources and times, never a verdict (reports/065).

Hermetic: every network check is monkeypatched. The load-bearing assertions:
  * an indexed employer gets its own-system facts and the date semantics it deserves;
  * a known-not-indexed employer gets that record, a ceased one gets no domain checks;
  * a vendor-hosted careers page yields no domain to check unless the caller passes one;
  * the register is `pending_user` without a key and names the ways to get it, and is
    `verified` with a key through the injected fetch, never invented;
  * the tool is registered read-only and open-world, says it is not a verdict, and sends
    nothing about the user anywhere (no fingerprint, no résumé field, no key echoed back).
"""

from __future__ import annotations

import asyncio
import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from openhire import mcp_server, service
from openhire.db.models import Base, Company, Job
from openhire.errors import OpenHireError
from openhire.verify import checks, employer_check, tianyancha

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 8, tzinfo=UTC)
EM_DASH = chr(0x2014)
REAL_FETCH = tianyancha.fetch_baseinfo  # captured before the autouse fixture replaces it
REAL_DOMAIN_AGE, REAL_WAYBACK, REAL_HOMEPAGE = checks.domain_age, checks.wayback_first_capture, checks.homepage_check


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        s.add(Company(id="minieye", name="佑驾创新 MINIEYE", ats_vendor="moka", ats_tenant="minieye/118570",
                      careers_url="https://app.mokahr.com/apply/minieye/118570", last_crawled_at=NOW))
        s.add(Company(id="lixiang", name="理想汽车 Li Auto", ats_vendor="lixiang", ats_tenant="social",
                      careers_url="https://www.lixiang.com/employ/social.html", last_crawled_at=NOW))
        for i in range(3):
            s.add(Job(id=f"minieye:{i}", company_id="minieye", title="感知算法工程师", description_raw="x",
                      skills=["perception"], remote_policy="onsite", location="北京",
                      posted_at=NOW - dt.timedelta(days=10 * (i + 1)), first_seen_at=NOW, verified_at=NOW,
                      source="ats_public_api", apply_channel=f"https://app.mokahr.com/apply/minieye/118570#/job/{i}",
                      content_hash=f"h{i}", ghost_score=0.0, role_family="engineering"))
        s.add(Job(id="lixiang:1", company_id="lixiang", title="自动驾驶感知算法工程师", description_raw="x",
                  skills=["perception"], remote_policy="onsite", location="北京", posted_at=None,
                  first_seen_at=NOW - dt.timedelta(days=15), verified_at=NOW, source="ats_public_api",
                  apply_channel="https://www.lixiang.com/employ/detail/1.html", content_hash="h", ghost_score=0.0,
                  role_family="engineering"))
        s.commit()
        yield s


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Deterministic stand-ins for every network check (looked up at call time)."""
    monkeypatch.setattr(checks, "domain_age", lambda d: {"status": "verified", "registered": "2018-03-01", "age_days": 3000, "note": "域名注册于 2018-03-01"})
    monkeypatch.setattr(checks, "wayback_first_capture", lambda d: {"status": "verified", "first_capture": "2018-05-01", "age_days": 2900, "note": "首次抓取 2018-05-01"})
    monkeypatch.setattr(checks, "homepage_check", lambda d, icp=None, name=None: {"status": "verified", "icp_on_page": ["京ICP备12345678号"], "name_on_page": True, "note": "首页页脚有备案号"})
    monkeypatch.setattr(tianyancha, "fetch_baseinfo", lambda name, key=None: {"status": "pending_user", "note": "没有 TIANYANCHA_API_KEY"})


def _run(session, **kw):
    return service.employer_check(session, now=NOW, **kw)


# --- through the service (resolution + domain derivation) -----------------------------------
def test_indexed_employer_on_a_vendor_board_has_facts_but_no_domain_to_check(session):
    res = _run(session, company="minieye")
    by = {i["id"]: i for i in res["checks"]}
    assert by["in_index"]["status"] == "verified"
    assert by["in_index"]["active_jobs"] == 3 and by["in_index"]["posting_dates_reported"] is True
    assert by["domain"]["status"] == "not_applicable" and "domain" in by["domain"]["note"]
    assert by["registry_record"]["status"] == "pending_user"
    assert res["pending_user"][0]["id"] == "registry_record"
    ways = [h["way"] for h in res["pending_user"][0]["how"]]
    assert ways == ["tianyancha_key", "tianyancha_mcp", "manual_free", "manual_free_hk_overseas"]
    assert "aiqicha.baidu.com" in res["pending_user"][0]["how"][2]["steps"]
    # 0.8.2: a Hong Kong or overseas employer is not in the mainland register; the free ways
    # name the HK Companies Registry, the HK Police Scameter and OpenCorporates.
    hk = res["pending_user"][0]["how"][3]["steps"]
    assert "e-services.cr.gov.hk" in hk and "cyberdefender.hk/scameter" in hk and "opencorporates.com" in hk
    assert res["summary"]["pending_user"] == 1


def test_first_party_employer_derives_its_own_domain_and_dates_are_marked(session):
    res = _run(session, company="理想")
    by = {i["id"]: i for i in res["checks"]}
    assert res["domain"] == "lixiang.com"
    assert by["in_index"]["posting_dates_reported"] is False and "首次抓到" in by["in_index"]["note"]
    assert by["domain_age"]["status"] == "verified" and by["domain_age"]["registered"] == "2018-03-01"
    assert "reason" in by["domain_age"] and "reason" in by["site_history"] and "reason" in by["icp_on_homepage"]
    assert by["site_history"]["source"].startswith("Internet Archive")
    assert by["icp_on_homepage"]["icp_on_page"] == ["京ICP备12345678号"]


def test_explicit_domain_overrides_and_bad_queries_are_refused(session):
    res = _run(session, company="minieye", domain="https://www.minieye.cc/careers")
    assert res["domain"] == "minieye.cc"
    assert {i["id"] for i in res["checks"]} >= {"domain_age", "site_history", "icp_on_homepage"}
    session.add(Company(id="lixin", name="理信科技", ats_vendor="moka", ats_tenant="x", careers_url="x", last_crawled_at=NOW))
    session.commit()
    with pytest.raises(OpenHireError) as ei:
        _run(session, company="理")
    assert ei.value.code == "ERR_AMBIGUOUS_COMPANY"
    with pytest.raises(OpenHireError) as ei:
        _run(session)
    assert ei.value.code == "ERR_BAD_QUERY"


def test_known_not_indexed_employer_gets_its_record_and_no_vendor_domain(session):
    res = _run(session, company="Momenta")
    by = {i["id"]: i for i in res["checks"]}
    assert by["known_not_indexed"]["status"] == "not_applicable"
    assert "签名" in by["known_not_indexed"]["note"] or "访问控制" in by["known_not_indexed"]["note"]
    # momenta.jobs.feishu.cn is the vendor's host, not the employer's domain.
    assert res["domain"] is None and by["domain"]["status"] == "not_applicable"
    assert by["registry_record"]["status"] == "pending_user"


def test_ceased_employer_gets_the_fact_and_nothing_to_check(session):
    res = _run(session, company="毫末")
    by = {i["id"]: i for i in res["checks"]}
    assert by["ceased_operations"]["status"] == "verified" and "停止运营" in by["ceased_operations"]["note"]
    assert by["domain"]["status"] == "not_applicable" and by["registry_record"]["status"] == "not_applicable"
    assert res["pending_user"] == []


def test_unknown_company_with_a_domain_still_gets_domain_checks(session):
    res = _run(session, company="不存在的机器人公司", domain="nobody-robotics.cn")
    by = {i["id"]: i for i in res["checks"]}
    assert by["in_index"]["status"] == "not_verified" and "不说明它有问题" in by["in_index"]["note"]
    assert by["domain_age"]["status"] == "verified"
    res = _run(session, domain="nobody-robotics.cn")
    assert {i["id"] for i in res["checks"]} >= {"in_index", "domain_age", "site_history", "icp_on_homepage"}


def test_posting_red_flags_are_listed_not_judged(session):
    res = _run(session, company="minieye", posting_text="海外高薪客服，包机票包吃住，无需经验")
    by = {i["id"]: i for i in res["checks"]}
    assert by["posting_red_flags"]["status"] == "not_verified"
    assert by["posting_red_flags"]["flags"] == ["海外高薪", "包机票", "包吃住", "无需经验"]
    res = _run(session, company="minieye", posting_text="负责 BEV 感知模型开发，3 年以上经验。")
    assert {i["id"]: i for i in res["checks"]}["posting_red_flags"]["status"] == "verified"


def test_register_with_the_users_key_is_verified_through_the_fetch_never_invented(session, monkeypatch):
    monkeypatch.setattr(tianyancha, "fetch_baseinfo", lambda name, key=None: {
        "status": "verified", "record": {"name": name, "reg_status": "存续", "established": "2013-03-01", "insured_staff": 120},
        "note": "登记在册：存续，成立 2013-03-01，参保人数 120", "source": "天眼查 OpenAPI（你自己的 key，T+1）"})
    res = _run(session, company="minieye")
    by = {i["id"]: i for i in res["checks"]}
    assert by["registry_record"]["status"] == "verified" and by["registry_record"]["record"]["insured_staff"] == 120
    assert res["pending_user"] == []


def test_offline_run_marks_network_items_unavailable(session):
    res = _run(session, company="理想", run_network=False)
    by = {i["id"]: i for i in res["checks"]}
    assert by["domain"]["status"] == "unavailable" and by["registry_record"]["status"] == "unavailable"


def test_network_failure_is_named_as_the_network_not_as_a_missing_record(monkeypatch):
    """0.8.2 (reports/068): run from a restricted network, every domain item came back
    'RDAP 查不到注册日期' as if the registry had no record. A GET that never reached the
    source says nothing about the employer, so it carries reason=network and says so."""
    monkeypatch.setattr(checks, "_get", lambda url, timeout=None: None)
    for fn in (REAL_DOMAIN_AGE, REAL_WAYBACK, REAL_HOMEPAGE):
        out = fn("example.com")
        assert out["status"] == "unavailable" and out["reason"] == "network" and "没有连上" in out["note"], fn.__name__

    class Answered:  # the source was reached and has nothing
        status_code = 404
        text = ""

    monkeypatch.setattr(checks, "_get", lambda url, timeout=None: Answered())
    assert REAL_DOMAIN_AGE("example.com")["reason"] == "no_record"
    assert REAL_WAYBACK("example.com")["reason"] == "http_status"
    assert REAL_HOMEPAGE("example.com")["reason"] == "http_status"


def test_job_id_resolves_the_employer_and_screens_the_stored_posting(session):
    """0.8.2 (reports/068): the assistant checks the role it just found by job_id; the
    employer comes from the row and the red-flag screen reads the stored title and JD."""
    session.add(Job(id="minieye:bad", company_id="minieye", title="海外客服", description_raw="包机票包吃住，无需经验，日结",
                    skills=[], remote_policy="onsite", location="柬埔寨", posted_at=NOW, first_seen_at=NOW, verified_at=NOW,
                    source="ats_public_api", apply_channel="https://app.mokahr.com/apply/minieye/118570#/job/bad",
                    content_hash="hb", ghost_score=0.0, role_family=None))
    session.commit()
    res = _run(session, job_id="minieye:bad")
    by = {i["id"]: i for i in res["checks"]}
    assert res["company"] == "佑驾创新 MINIEYE" and res["query"]["posting_text_source"] == "index"
    assert by["posting_red_flags"]["status"] == "not_verified" and "包机票" in by["posting_red_flags"]["flags"]
    clean = _run(session, job_id="minieye:0")
    assert {i["id"]: i for i in clean["checks"]}["posting_red_flags"]["status"] == "verified"
    given = _run(session, job_id="minieye:bad", posting_text="负责 BEV 感知模型开发")
    assert given["query"]["posting_text_source"] == "user"
    assert {i["id"]: i for i in given["checks"]}["posting_red_flags"]["status"] == "verified"
    with pytest.raises(OpenHireError) as ei:
        _run(session, job_id="nobody:1")
    assert ei.value.code == "ERR_JOB_NOT_FOUND"


def test_traditional_character_lures_are_flagged_like_the_simplified_ones():
    flags = checks.red_flags_in("海外高薪，包機票包食宿，無需經驗，日結")
    assert flags == ["海外高薪", "包機票", "包食宿", "日結", "無需經驗"]  # tuple order, not text order
    assert checks.red_flags_in("Senior Perception Engineer, Hong Kong. 5+ years, LiDAR fusion.") == []


def test_tianyancha_envelope_handling_without_network(monkeypatch):
    class R:
        def __init__(self, status, body):
            self.status_code = status
            self._b = body

        def json(self):
            return self._b

    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append((url, params, headers))
        return R(200, {"error_code": 0, "reason": "ok", "result": {
            "name": "佑驾创新", "regStatus": "存续", "estiblishTime": 1362096000000, "socialStaffNum": 120,
            "creditCode": "9144", "legalPersonName": "x"}})

    monkeypatch.setattr(tianyancha.httpx, "get", fake_get)
    out = REAL_FETCH("佑驾创新", key="k")
    assert out["status"] == "verified" and out["record"]["established"] == "2013-03-01"
    assert calls[0][2]["Authorization"] == "k" and calls[0][1] == {"keyword": "佑驾创新"}
    monkeypatch.setattr(tianyancha.httpx, "get", lambda *a, **k: R(200, {"error_code": 300001, "reason": "余额不足"}))
    assert REAL_FETCH("x", key="k")["status"] == "unavailable"
    monkeypatch.setattr(tianyancha.httpx, "get", lambda *a, **k: R(200, {"error_code": 0, "result": {}}))
    assert REAL_FETCH("x", key="k")["status"] == "not_verified"
    monkeypatch.delenv(tianyancha.ENV_KEY, raising=False)
    assert REAL_FETCH("x")["status"] == "pending_user"


# --- the MCP boundary -----------------------------------------------------------------------
def test_tool_is_registered_read_only_open_world_and_says_it_is_not_a_verdict():
    from mcp.shared.memory import create_connected_server_and_client_session as connect

    async def _tools():
        async with connect(mcp_server.mcp) as client:
            return {t.name: t for t in (await client.list_tools()).tools}

    tools = asyncio.run(_tools())
    t = tools["check_employer"]
    assert t.annotations.readOnlyHint is True and t.annotations.openWorldHint is True
    doc = " ".join((mcp_server.check_employer.__doc__ or "").split())
    for phrase in ("Never a score", "pending_user", "TIANYANCHA_API_KEY", "Nothing about the user"):
        assert phrase in doc, phrase
    # 0.8.1: an assistant that already has a 天眼查 tool (Tencent WorkBuddy ships one) fills
    # the register itself; it must not send the user off to buy a key first.
    assert "use it to fill `registry_record` directly instead of sending the user off to apply for a key" in doc
    assert "WorkBuddy" in doc
    assert EM_DASH not in doc and EM_DASH not in employer_check.NOT_A_VERDICT
    assert set(t.inputSchema["properties"]) == {"company", "domain", "posting_text", "job_id"}
    assert "job_id" in doc and "reason" in doc


def test_result_carries_no_user_data_and_no_key(session, monkeypatch):
    monkeypatch.setenv(tianyancha.ENV_KEY, "secret-key-value")
    res = _run(session, company="minieye")
    blob = str(res)
    assert "secret-key-value" not in blob
    for forbidden in ("fingerprint", "resume", "résumé"):
        assert forbidden not in blob.lower()
    assert res["not_a_verdict"].startswith("These are facts")
