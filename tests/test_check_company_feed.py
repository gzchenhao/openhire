"""The 查公司 feed EarlyTip renders as its own column (reports/095).

EarlyTip fetches docs/check-company.json on a schedule and re-renders when `sha256` moves,
so nobody has to tell it the page changed. That only works if the feed always matches the
page, and EarlyTip's conditions (reports/088) hold for the feed as they do for the page."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from openhire import check_company_feed as feed
from openhire import hosted

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "check-company.html"
DOCS_FEED = ROOT / "docs" / "check-company.json"


def test_docs_feed_is_regenerated_from_the_page():
    expected = feed.dumps(feed.build(PAGE.read_text(encoding="utf-8")))
    assert DOCS_FEED.read_text(encoding="utf-8") == expected, (
        "docs/check-company.json is stale: run python scripts/build_check_company_feed.py")


def test_feed_keeps_earlytips_conditions():
    d = json.loads(DOCS_FEED.read_text(encoding="utf-8"))
    assert d["schema"] == 1 and d["title"] == "查公司"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", d["updated"])
    body = d["html"]
    for banned in ("求职", "招聘", "岗位", "uvx", "/mcp", "安装", "checklist"):
        assert banned not in body, banned
    assert "openhire" not in body.lower(), "no product name in what EarlyTip renders"
    assert "gsxt.gov.cn" in body and "beian.miit.gov.cn" in body and "cyberdefender.hk" in body
    assert "<h2>二、识别骗局，三步</h2>" in body
    assert d["feedback_url"] == "https://github.com/gzchenhao/openhire/issues"


def test_feed_html_is_sanitized_by_construction():
    body = json.loads(DOCS_FEED.read_text(encoding="utf-8"))["html"]
    for tag, attrs in re.findall(r"<([a-z0-9]+)([^>]*)>", body):
        assert tag in feed.ALLOWED_TAGS, tag
        if tag == "a":
            assert re.fullmatch(r' href="https://[^"<>]+"', attrs), attrs
        else:
            assert attrs == "", (tag, attrs)


@pytest.mark.parametrize("hostile", [
    '<p>x<script>alert(1)</script></p>',
    '<p><a href="javascript:alert(1)">x</a></p>',
    '<p onclick="x()"><img src=x onerror=y()>&lt;b&gt;</p>',
    '<p><a href="http://plain.example/">x</a><iframe src="https://e.example/"></iframe></p>',
])
def test_sanitizer_drops_everything_outside_the_whitelist(hostile):
    page = f"<h1>查公司</h1><p>最后更新 2026-10-27。</p>{hostile}<hr><p>footer</p>"
    body = feed.build(page)["html"]
    assert "<script" not in body and "<img" not in body and "<iframe" not in body
    assert "javascript:" not in body and "onclick" not in body and "http://" not in body
    assert "footer" not in body and "alert" not in body
    assert body.count("<a ") == body.count("</a>"), "no orphan closing tag for a dropped link"
    if "&lt;b&gt;" in hostile:
        assert "&lt;b&gt;" in body, "text that looks like markup stays text"


def test_sha256_moves_when_the_content_moves():
    page = PAGE.read_text(encoding="utf-8")
    a = feed.build(page)["sha256"]
    b = feed.build(page.replace("裁判文书网", "裁判文书网（示例）"))["sha256"]
    assert a != b and feed.build(page)["sha256"] == a


def test_page_links_stay_in_step_with_the_checklist():
    """查公司 repeats the checklist's company-check and anti-scam steps. When an official
    address changes in the checklist, the old one here turns this test red, so the two pages
    (and EarlyTip's column with them) cannot drift apart."""
    links = lambda p: set(re.findall(r'href="(https://[^"]+)"', p.read_text(encoding="utf-8")))
    missing = links(PAGE) - links(ROOT / "docs" / "checklist.html") - {feed.FEEDBACK_URL}
    assert not missing, f"in check-company.html but not in checklist.html: {sorted(missing)}"


def test_hosted_endpoint_serves_the_same_feed():
    from starlette.testclient import TestClient

    from openhire.mcp_server import mcp

    r = TestClient(hosted.build_app(mcp)).get("/check-company.json")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/json")
    assert r.headers["access-control-allow-origin"] == "*"
    assert r.text == DOCS_FEED.read_text(encoding="utf-8")


# --- EarlyTip's own two gates (reports/099) ------------------------------------------------
# The column went live on 2026-10-28 with two checks of EarlyTip's own: the visible text must
# not contain any of six words, and a new version must not be shorter than half of the one
# shown. Both run on our side first, so nothing EarlyTip would refuse is ever published.


def test_docs_feed_passes_earlytips_gates():
    d = json.loads(DOCS_FEED.read_text(encoding="utf-8"))
    assert feed.earlytip_gate(d, previous=d) == []


@pytest.mark.parametrize("word", ["求职", "招聘", "岗位", "MCP", "安装", "OpenHire", "openhire"])
def test_gate_catches_each_banned_word_in_the_visible_text(word):
    bad = {"html": f"<p>这里提到 {word} 一次。</p>"}
    problems = feed.earlytip_gate(bad)
    assert len(problems) == 1 and word.lower() in problems[0].lower(), problems


def test_gate_reads_the_visible_text_the_way_earlytip_does():
    # EarlyTip checks what a reader sees; our own stricter test above still bans the product
    # name anywhere in the html, hrefs included, so this only documents the gate's scope.
    hidden = {"html": '<p>看 <a href="https://example.com/openhire">这里</a>。</p>'}
    assert feed.earlytip_gate(hidden) == []
    assert feed.visible_text("<p>a &amp; b</p><table><tr><td>c</td></tr></table>").split() == ["a", "&", "b", "c"]


def test_gate_refuses_a_shrink_past_half_but_not_a_smaller_one():
    previous = {"html": "x" * 2000}
    assert feed.earlytip_gate({"html": "y" * 1100}, previous) == []
    problems = feed.earlytip_gate({"html": "y" * 900}, previous)
    assert len(problems) == 1 and "2000 to 900" in problems[0]
    assert feed.earlytip_gate({"html": "y" * 900}) == [], "no previous version, no length gate"


def test_build_script_refuses_a_shrunken_page_unless_allowed(tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location("build_feed", ROOT / "scripts" / "build_check_company_feed.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "check-company.html").write_text(
        "<h1>查公司</h1><p>最后更新 2026-10-28。</p><p>短。</p><hr><p>footer</p>", encoding="utf-8")
    long_feed = {"html": "<p>" + "很长的一段。" * 200 + "</p>"}
    (docs / "check-company.json").write_text(json.dumps(long_feed, ensure_ascii=False), encoding="utf-8")
    assert mod.main(tmp_path) == 1
    assert json.loads((docs / "check-company.json").read_text(encoding="utf-8")) == long_feed, "refused means untouched"
    assert mod.main(tmp_path, allow_shrink=True) == 0
    assert "短。" in json.loads((docs / "check-company.json").read_text(encoding="utf-8"))["html"]
    # The word gate is never waived.
    (docs / "check-company.html").write_text(
        "<h1>查公司</h1><p>最后更新 2026-10-28。</p><p>这页讲 OpenHire。</p><hr>", encoding="utf-8")
    assert mod.main(tmp_path, allow_shrink=True) == 1
