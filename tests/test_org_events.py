"""The EarlyTip org_events export as `check_employer` reads it (reports/077).

OpenHire is the consumer side of a file another project produces, so what is pinned here is
the reader's contract with the published spec, not the producer's behaviour:
  * `company_key` is the spec's algorithm, step for step, on the spec's own examples;
  * `event_id` normalises the URL fragment, surrounding space and the 待核实 marker away;
  * the file is read whole, cached for a day, and a network failure says `network`;
  * an employer matches as subject (by key or alias) or counterparty, retracted rows and
    rows without a company are never shown, and what is shown is type, date, domain and
    link: never the headline, and no link for a site whose terms prohibit linking;
  * the checklist item carries the registry aliases into the match and says `no_record`
    when the file holds nothing, which is not a mark against the employer;
  * the maintainer audit recomputes ids and keys and flags what breaks the spec, while
    counting what the spec allows (a null company) without calling it a problem.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import types

import pytest
from typer.testing import CliRunner

from openhire import config, mcp_server
from openhire.cli import app
from openhire.verify import checks, employer_check, org_events

UTC = dt.timezone.utc


def _ev(**kw) -> dict:
    base = {
        "event_id": None, "company": None, "company_key": None, "company_aliases": None, "related_companies": None,
        "event_type": "融资进展", "event_date": None, "published_date": "2026-09-24", "amount": None,
        "title": "t", "url": "https://36kr.com/p/1", "source": None, "unverified": False,
        "captured_at": "2026-10-14T09:49:49+07:00", "backfilled": True, "retracted": False,
        "retracted_at": None, "retraction_reason": None,
    }
    base.update(kw)
    if base["event_id"] is None:
        base["event_id"] = org_events.event_id(base["url"], base["title"])
    if base["company_key"] is None and base["company"]:
        base["company_key"] = org_events.company_key(base["company"])
    if base["source"] is None:
        base["source"] = checks.normalise_domain(base["url"])
    return base


def _export(events: list[dict]) -> dict:
    return {"schema_version": 1, "generated_at": "2026-10-14T09:49:49+07:00", "event_count": len(events), "events": events}


@pytest.fixture()
def export() -> dict:
    return _export([
        _ev(company="高通", event_type="对外M&A", related_companies=["PickNik Robotics"], title="高通收购PickNik Robotics",
            url="https://www.therobotreport.com/qualcomm-picknik", published_date="2026-09-24"),
        _ev(company="地瓜机器人", amount="数亿元", title="地瓜机器人完成数亿元A轮融资",
            url="https://t.cj.sina.com.cn/articles/view/123", published_date="2026-09-24"),
        _ev(company="Boston Dynamics", company_aliases=["波士顿动力"], event_type="高管流动", related_companies=["亚马逊"],
            event_date="2026-10-06", published_date="2026-10-07", unverified=True,
            title="亚马逊前高管加入Boston Dynamics（待核实）", url="https://biz.chosun.com/x"),
        _ev(company="特斯拉", event_type="组织架构调整", title="特斯拉撤销Dojo团队", url="https://ai-damn.com/t",
            published_date="2026-09-22", retracted=True, retracted_at="2026-10-01T09:00:00+08:00", retraction_reason="来源撤稿"),
        _ev(company=None, event_type="大佬离职", title="TuSimple联合创始人离开", url="https://techshotsapp.com/a", published_date="2026-09-22"),
        _ev(company="理想汽车", event_type="组织架构调整", title="理想汽车调整组织架构", url="https://www.163.com/dy/article/x.html",
            published_date="2026-10-10"),
    ])


@pytest.fixture()
def home(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CLIENT_HOME", tmp_path)
    return tmp_path


def _resp(data: dict, status: int = 200):
    return types.SimpleNamespace(status_code=status, text=json.dumps(data, ensure_ascii=False))


# --- the published key and id ----------------------------------------------------------------
def test_company_key_follows_the_published_rule_step_for_step():
    cases = {
        "Boston Dynamics": "bostondynamics",          # separators removed
        "Minerva Humanoids": "minervahumanoids",
        "Dulo, Inc.": "dulo",                         # Latin legal form stripped, then punctuation
        "Agile Robots AG": "agilerobots",
        "Robotec.ai": "robotecai",
        "Tesla": "tesla",
        "深圳市优必选科技股份有限公司": "深圳市优必选科技",   # longest Chinese suffix first
        "小米集团有限公司": "小米",                       # stripped repeatedly
        "京东探索研究院": "京东探索研究院",
        "ＴｕＳｉｍｐｌｅ": "tusimple",                  # NFKC then casefold
        "理想汽车 Li Auto": "理想汽车liauto",
        "公司": "",                                     # empty: the producer refuses such a row
        None: "",
    }
    for name, key in cases.items():
        assert org_events.company_key(name) == key, name


def test_event_id_is_the_spec_hash_with_fragment_space_and_marker_normalised_away():
    expected = hashlib.sha256("https://x.test/a\n高通收购PickNik".encode()).hexdigest()[:16]
    assert org_events.event_id("https://x.test/a", "高通收购PickNik") == expected
    assert org_events.event_id(" https://x.test/a#top ", "高通收购PickNik（待核实） ") == expected
    assert org_events.event_id("https://x.test/a", "高通收购PickNik(待核实)") == expected
    assert org_events.event_id("https://x.test/b", "高通收购PickNik") != expected


def test_name_variants_split_a_bilingual_name_and_keep_aliases():
    assert org_events.name_variants("理想汽车 Li Auto", ["LiAuto"]) == ["理想汽车 Li Auto", "Li Auto", "理想汽车", "LiAuto"]
    assert org_events.name_variants(None) == []


def test_links_are_withheld_for_sites_whose_terms_list_linking_as_prohibited():
    for host in ("t.cj.sina.com.cn", "finance.sina.com.cn", "cls.cn", "www.bloomberg.com", "cs.com.cn", "chinastarmarket.cn", "reuters.com"):
        assert not org_events.link_allowed(host), host
    for host in ("36kr.com", "m.toutiao.com", "163.com", "notsina.com.cn", "news.qq.com"):
        assert org_events.link_allowed(host), host
    assert not org_events.link_allowed(None)


# --- reading the file ---------------------------------------------------------------------------
def test_parse_refuses_other_schemas_and_things_that_are_not_the_export():
    assert org_events.parse("nope")["error"] == "not_json"
    assert org_events.parse("[1, 2]")["error"] == "not_the_export"
    assert org_events.parse(json.dumps({"schema_version": 1, "nope": []}))["error"] == "not_the_export"
    other = org_events.parse(json.dumps({"schema_version": 2, "events": []}))
    assert other["error"] == "schema_version" and other["schema_version"] == 2
    assert "error" not in org_events.parse(json.dumps({"schema_version": 1, "events": []}))


def test_load_reads_once_a_day_and_a_failure_names_the_network_not_the_data(home, monkeypatch, export):
    calls = []

    def fake_get(url, timeout=None):
        calls.append(url)
        return _resp(export)

    monkeypatch.setattr(checks, "_get", fake_get)
    data = org_events.load()
    assert calls == [org_events.URL] and data["event_count"] == 6 and data["downloaded"] == dt.date.today().isoformat()
    org_events.load()
    assert len(calls) == 1, "the second read within a day comes from the cache"

    monkeypatch.setattr(checks, "_get", lambda url, timeout=None: None)
    assert "error" not in org_events.load(), "a cached copy is served while the network is down"
    (home / "earlytip" / "org_events.json").unlink()
    assert org_events.load()["error"] == "network"
    assert org_events.load(allow_network=False)["error"] == "offline"
    monkeypatch.setattr(checks, "_get", lambda url, timeout=None: _resp({}, 503))
    assert org_events.load()["error"] == "http_status"
    monkeypatch.setattr(checks, "_get", lambda url, timeout=None: _resp({"schema_version": 2, "events": []}))
    assert org_events.load()["error"] == "schema_version"
    assert not (home / "earlytip" / "org_events.json").exists(), "a file of another schema is never cached"


# --- matching and the shown shape -------------------------------------------------------------
def test_events_match_by_key_alias_or_counterparty_and_skip_retracted_and_nameless_rows(export):
    assert [e["event_type"] for e in org_events.events_for(export, "Qualcomm 高通")] == ["对外M&A"]
    assert org_events.events_for(export, "高通")[0]["role"] == "subject"
    picknik = org_events.events_for(export, "PickNik Robotics, Inc.")
    assert len(picknik) == 1 and picknik[0]["role"] == "counterparty" and picknik[0]["company"] == "高通"
    assert org_events.events_for(export, "波士顿动力")[0]["company"] == "Boston Dynamics", "matched through the export's alias"
    assert org_events.events_for(export, "亚马逊")[0]["role"] == "counterparty"
    assert org_events.events_for(export, "特斯拉") == [], "retracted rows are never shown"
    assert org_events.events_for(export, "TuSimple") == [], "a row the export could not name is skipped"
    assert org_events.events_for(export, "公司") == [] and org_events.events_for(export, None) == []
    # The index's bilingual display name matches on either half.
    assert org_events.events_for(export, "理想汽车 Li Auto")[0]["event_type"] == "组织架构调整"


def test_a_glued_bilingual_name_in_the_export_matches_on_either_half():
    # The first export (2026-10-14) wrote 庞伯特Pongbot as one word; a seeker types either half,
    # and a counterparty written the same way must land too.
    data = _export([
        _ev(company="庞伯特Pongbot", title="庞伯特完成融资", url="https://36kr.com/p/7", published_date="2026-10-12"),
        _ev(company="京东", event_type="大佬离职", related_companies=["贝塔无限 Beta Infinity"], title="t2",
            url="https://www.163.com/dy/article/y.html", published_date="2026-09-24"),
    ])
    assert org_events.events_for(data, "Pongbot")[0]["company"] == "庞伯特Pongbot"
    assert org_events.events_for(data, "庞伯特")[0]["company"] == "庞伯特Pongbot"
    assert org_events.events_for(data, "Beta Infinity")[0]["role"] == "counterparty"
    assert org_events.events_for(data, "贝塔无限")[0]["role"] == "counterparty"
    assert org_events.events_for(data, "Infinity") == [], "a bare word is not a half: no over-matching"


def test_what_is_shown_is_type_date_domain_and_link_and_never_the_title(export):
    sina = org_events.events_for(export, "地瓜机器人")[0]
    assert sina["url"] is None and sina["link_withheld"] and sina["source"] == "t.cj.sina.com.cn"
    assert "title" not in sina and sina["amount"] == "数亿元" and "地瓜机器人完成" not in json.dumps(sina, ensure_ascii=False)
    assert sina["date"] == "2026-09-24" and sina["date_kind"] == "published_date"
    bd = org_events.events_for(export, "Boston Dynamics")[0]
    assert bd["url"] == "https://biz.chosun.com/x" and bd["link_withheld"] is None
    assert bd["date"] == "2026-10-06" and bd["date_kind"] == "event_date" and bd["unverified"] is True
    assert bd["related_companies"] == ["亚马逊"] and bd["backfilled"] is True and bd["amount"] is None


def test_screen_statuses_say_what_was_read_and_never_judge(export):
    none = org_events.screen(None, data=export)
    assert none["status"] == "not_applicable"
    empty = org_events.screen("宇树科技 Unitree", data=export)
    assert empty["status"] == "unavailable" and empty["reason"] == "no_record" and "不说明任何事" in empty["note"]
    hit = org_events.screen("高通", data=export)
    assert hit["status"] == "verified" and hit["total"] == 1 and hit["events"][0]["event_type"] == "对外M&A"
    assert "对外M&A 1" in hit["note"] and org_events.PROVENANCE in hit["note"] and "therobotreport.com" in hit["note"]
    assert hit["generated_at"] == export["generated_at"]
    fund = org_events.screen("地瓜机器人", data=export)
    assert "融资进展（数亿元）" in fund["note"], "the amount rides the note since 0.8.9"
    down = org_events.screen("高通", data={"error": "network"})
    assert down["status"] == "unavailable" and down["reason"] == "network" and "不是雇主" in down["note"]
    old = org_events.screen("高通", data={"error": "schema_version", "schema_version": 2})
    assert old["reason"] == "schema_version" and "只读 1" in old["note"]


def test_screen_caps_the_shown_events_and_reports_the_total():
    many = _export([_ev(company="宇树", title=f"宇树第{i}轮", url=f"https://36kr.com/p/{i}", published_date=f"2026-10-{i + 1:02d}")
                    for i in range(25)])
    hit = org_events.screen("宇树", data=many)
    assert hit["total"] == 25 and len(hit["events"]) == org_events.MAX_SHOWN
    assert hit["events"][0]["date"] == "2026-10-25", "newest first"


# --- the checklist item --------------------------------------------------------------------------
def test_checklist_carries_the_item_with_the_registry_aliases_and_the_network_switch():
    seen = {}

    def spy(name, aliases=(), allow_network=True):
        seen.update(name=name, aliases=aliases, allow_network=allow_network)
        return {"status": "verified", "note": "n", "source": "s", "events": [{"event_type": "x"}], "total": 1,
                "generated_at": "2026-10-14T09:49:49+07:00", "downloaded": "2026-10-14"}

    known = {"name": "蔚来 NIO", "aliases": ["nio", "蔚来汽车"], "ats": "feishu", "reason_zh": "飞书", "careers_url": None}
    res = employer_check.build_checklist(query={"company": "蔚来"}, index_facts=None, known_not_indexed=known, domain=None,
                                         run_network=False, org_events_fn=spy)
    assert seen == {"name": "蔚来 NIO", "aliases": ("nio", "蔚来汽车"), "allow_network": False}
    item = next(i for i in res["checks"] if i["id"] == "org_events")
    assert item["status"] == "verified" and item["total"] == 1 and item["events"] == [{"event_type": "x"}]
    assert item["file_generated_at"].startswith("2026-10-14") and item["file_downloaded"] == "2026-10-14"
    assert "EarlyTip" in res["privacy"] and "whole" in res["privacy"]

    res = employer_check.build_checklist(query={"domain": "x.test"}, index_facts=None, known_not_indexed=None, domain="x.test",
                                         run_network=False, org_events_fn=spy)
    assert next(i for i in res["checks"] if i["id"] == "org_events")["status"] == "not_applicable"


def test_the_default_item_reads_through_the_module_and_the_tool_doc_names_it(home, monkeypatch, export):
    monkeypatch.setattr(checks, "_get", lambda url, timeout=None: _resp(export))
    res = employer_check.build_checklist(query={"company": "高通"}, index_facts={"company": "高通", "active_jobs": 1, "median_days_open": 3,
                                                                                    "posting_dates_reported": True},
                                         known_not_indexed=None, domain=None, run_network=True,
                                         domain_age_fn=lambda d: {}, wayback_fn=lambda d: {}, homepage_fn=lambda d, i, n: {},
                                         register_fn=lambda n: {"status": "pending_user", "note": ""},
                                         sanctions_fn=lambda n, aliases=(), allow_network=True: {"status": "verified", "note": "", "matches": []})
    item = next(i for i in res["checks"] if i["id"] == "org_events")
    assert item["status"] == "verified" and item["events"][0]["related_companies"] == ["PickNik Robotics"]
    doc = mcp_server.check_employer.__doc__ or ""
    for phrase in ("org_events", "company_key", "link_withheld", "never the headline", "no_record", "amount"):
        assert phrase in doc, phrase


# --- the maintainer audit ---------------------------------------------------------------------------
def test_audit_recomputes_ids_and_keys_and_flags_what_breaks_the_spec(export):
    clean = org_events.audit(export)
    assert clean["count_matches"] and clean["event_count_actual"] == 6 and clean["problem_count"] == 0
    assert clean["retracted"] == 1 and clean["company_null"] == 1 and clean["unverified"] == 1
    assert clean["with_event_date"] == 1 and clean["with_amount"] == 1 and clean["with_related"] == 2
    assert clean["no_link_sources"] == {"t.cj.sina.com.cn": 1} and clean["event_types"]["组织架构调整"] == 2
    assert clean["published_range"] == ["2026-09-22", "2026-10-10"] and "高通" in clean["companies"]
    assert clean["problems"] == {"company_null": [export["events"][4]["event_id"]],
                                 "event_date_not_in_title": [export["events"][2]["event_id"]]}

    bad = _ev(company="某某（集团）", event_type="融资进展", related_companies=["某基金"], published_date="2026-10-01",
              event_date="2026/10/1", title="某某完成融资", url="https://www.cls.cn/x", source="cls.cn")
    bad["event_id"] = "0000000000000000"
    bad["company_key"] = "wrong"
    del bad["amount"]
    dup = dict(export["events"][0])
    shouted = _ev(company="甲", unverified=True, title="甲融资", url="https://36kr.com/p/9", published_date="2026-10-05")
    data = _export([*export["events"], bad, dup, shouted])
    data["event_count"] = 99
    out = org_events.audit(data)
    assert not out["count_matches"] and out["event_count_declared"] == 99
    p = out["problems"]
    assert p["missing_keys"] == ["0000000000000000"] and p["event_id_mismatch"] == ["0000000000000000"]
    assert p["company_key_mismatch"] == ["0000000000000000"] and p["company_has_brackets"] == ["0000000000000000"]
    assert p["event_date_format"] == ["0000000000000000"] and p["published_in_blackout"] == ["0000000000000000"]
    assert p["funding_with_related"] == ["0000000000000000"]
    assert p["event_id_duplicate"] == [export["events"][0]["event_id"]] * 2
    assert p["unverified_without_marker"] == [shouted["event_id"]]
    assert "source_mismatch" not in p and out["keys_with_two_companies"] == {}
    assert out["problem_count"] == 10


def test_cli_audit_reads_a_local_copy_and_prints_json(tmp_path, export):
    path = tmp_path / "org_events.json"
    path.write_text(json.dumps(export, ensure_ascii=False), encoding="utf-8")
    r = CliRunner().invoke(app, ["org-events-audit", "--file", str(path), "--json"])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert out["event_count_actual"] == 6 and out["problem_count"] == 0 and out["sources"]["163.com"] == 1
    assert set(out) >= {"problems", "companies", "no_link_sources", "event_types"}
    path.write_text(json.dumps({"schema_version": 2, "events": []}), encoding="utf-8")
    r = CliRunner().invoke(app, ["org-events-audit", "--file", str(path), "--json"])
    assert r.exit_code == 2 and json.loads(r.output)["error"] == "schema_version"


def test_compare_checks_the_append_only_promise_by_event_id(export):
    """The producer's 2026-10-15 note: the 83 original rows stay, 8 were added (3 of them
    backfilled with older dates), compare by event_id and never by date."""
    dropped = export["events"][1]
    fresh_one = _ev(company="星动纪元", title="星动纪元完成融资", url="https://36kr.com/p/9", backfilled=False)
    late_one = _ev(company="智元机器人", title="智元机器人组织调整", url="https://36kr.com/p/8", published_date="2026-10-13")
    current = _export([e for e in export["events"] if e is not dropped] + [fresh_one, late_one])
    out = org_events.compare(export, current, expect_at_least=8,
                             must_include=[late_one["event_id"], "53aa43e43fa14036"])
    assert out["baseline_count"] == 6 and out["current_count"] == 7
    assert out["baseline_ids_missing"] == [dropped["event_id"]] and not out["all_baseline_ids_present"]
    assert out["added_since_baseline"] == 2 and out["added_backfilled"] == 1
    assert out["count_ok"] is False and out["expected_at_least"] == 8
    assert out["must_include_missing"] == ["53aa43e43fa14036"]
    clean = org_events.compare(export, _export(export["events"] + [fresh_one]), expect_at_least=7)
    assert clean["all_baseline_ids_present"] and clean["count_ok"] and "must_include_missing" not in clean


def test_cli_fresh_keeps_the_replaced_copy_and_compares_against_it(tmp_path, export, monkeypatch):
    """`--fresh` used to delete the cached copy; the copy it replaces is the only record of
    what the file said before, so it is kept and the new download is checked against it."""
    monkeypatch.setattr(config, "CLIENT_HOME", tmp_path)
    org_events._cache_path().write_text(json.dumps(export, ensure_ascii=False), encoding="utf-8")
    newer = _export(export["events"] + [_ev(company="星动纪元", title="星动纪元完成融资", url="https://36kr.com/p/9")])
    monkeypatch.setattr(org_events, "load", lambda *a, **k: newer)
    r = CliRunner().invoke(app, ["org-events-audit", "--fresh", "--expect-at-least", "7",
                                 "--must-include", export["events"][0]["event_id"], "--json"])
    assert r.exit_code == 0, r.output
    cmp_ = json.loads(r.output)["comparison"]
    assert cmp_["baseline_count"] == 6 and cmp_["current_count"] == 7 and cmp_["all_baseline_ids_present"]
    assert cmp_["count_ok"] and cmp_["must_include_missing"] == []
    assert cmp_["baseline_file"].endswith("org_events.previous.json")
    assert org_events.previous_cache_path().exists() and not org_events._cache_path().exists()
