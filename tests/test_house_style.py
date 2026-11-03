"""Every OpenHire page carries the same look (house_style, from EarlyTip's layout spec,
2026-11-01). A page edited by hand, or a change to house_style.CSS without running
scripts/apply_house_style.py, turns this red."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from openhire import house_style

ROOT = Path(__file__).resolve().parents[1]
STATIC = ("index.html", "employers.html", "checklist.html", "connect.html")


def _apply_script():
    spec = importlib.util.spec_from_file_location("apply_house_style", ROOT / "scripts" / "apply_house_style.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("name", STATIC)
def test_static_pages_are_what_the_script_writes(name):
    page = (ROOT / "docs" / name).read_text(encoding="utf-8")
    key = name.removesuffix(".html")
    assert _apply_script().apply(page, key) == page, f"docs/{name} drifted: run python scripts/apply_house_style.py"
    assert house_style.CSS in page and house_style.nav(key) in page
    assert page.count("<main>") == 1 and page.count("</main>") == 1


def test_generated_pages_embed_the_house_style():
    from openhire import hosted, portals_page
    portals = portals_page.render()
    assert house_style.CSS in portals and house_style.nav("portals") in portals
    landing = hosted.landing_html()
    assert house_style.CSS in landing and house_style.nav("index") in landing


def test_the_house_style_follows_earlytips_spec():
    css = house_style.CSS
    for token in ("--bg:#f6f6f0", "--accent:#c0392b", "--link:#1a6496", "--border:#e0e0d8", "--max-w:860px",
                  '"PingFang SC","Microsoft YaHei"', "font-size:15px;line-height:1.75", "0 1px 3px rgba(0,0,0,.06)"):
        assert token in css, token
    assert "prefers-color-scheme" not in css and "@import" not in css, "no dark mode, no web fonts"


def test_nav_marks_only_the_current_page():
    bar = house_style.nav("checklist")
    assert bar.count('class="here"') == 1 and ">求职清单</span>" in bar
    assert 'href="connect.html"' in bar and 'href="checklist.html"' not in bar


@pytest.mark.parametrize("name", ("index.html", "employers.html", "portals.html", "checklist.html", "connect.html"))
def test_every_page_but_check_company_switches_language(name):
    """The maintainer found the portal directory, the employer page and the home pages had no
    中文 / English switch (2026-11-02). Every page carries one now; 查公司 stays Chinese only by
    EarlyTip's terms."""
    page = (ROOT / "docs" / name).read_text(encoding="utf-8")
    assert 'data-set="zh"' in page and 'data-set="en"' in page
    assert 'class="lang-zh"' in page and 'class="lang-en"' in page
    assert "openhire-lang" in page, "one remembered choice across pages"


def test_hosted_home_switches_language():
    from openhire import hosted
    page = hosted.landing_html()
    assert house_style.SWITCH in page and 'class="lang-zh"' in page and 'class="lang-en"' in page
