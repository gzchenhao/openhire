"""The blind-spot link directory (0.8.14): list_portals, `ohp portals`, docs/portals.html.

Howard, 2026-10-15: collect the portal links of the employers OpenHire cannot read so a
seeker clicks through, the way Zhihu links out. What these pin: the directory is the
registry (nothing fetched), a company that ceased operations is never a link, every entry
says what a browser shows without logging in and when it was last checked, the sector
filter takes what a seeker types, and the public page cannot drift from the registry."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from openhire import service
from openhire.cli import app
from openhire.errors import OpenHireError
from openhire.portals_page import render
from openhire.seed import not_indexed

ROOT = Path(__file__).resolve().parents[1]
EM_DASH = "—"


def test_directory_is_the_registry_minus_what_cannot_be_a_link():
    d = service.list_portals()
    names = [p["name"] for p in d["portals"]]
    assert d["count"] == len(names) == len([e for e in not_indexed.NOT_INDEXED if e.careers_url and not e.ceased])
    assert not any("毫末" in n for n in names)            # ceased: named on lookup, never a link
    assert not any("星动纪元" in n for n in names)        # indexed (Moka): a second portal, below
    seconds = d["also_on_portals_we_cannot_read"]
    assert [p["company_id"] for p in seconds] == ["robotera"]
    assert seconds[0]["careers_url"] == "https://k0fqxcszc9.jobs.feishu.cn/index" and "Moka" in seconds[0]["note"]
    for p in d["portals"]:
        assert p["careers_url"].startswith("https://")
        assert p["sector"] in not_indexed.SECTORS and p["sector_zh"]
        assert p["visible_without_login"] and p["visible_without_login_zh"]
        assert p["why_not_indexed"] and p["why_not_indexed_zh"]
        dt.date.fromisoformat(p["last_checked"])
        for v in p.values():
            assert EM_DASH not in str(v)
    assert "does not read, store, date or watch" in d["note"]
    assert "不读、不存、不标日期、不盯" in d["note_zh"]


@pytest.mark.parametrize("typed,sector", [
    ("具身", "embodied_ai"), ("Robotics", "embodied_ai"), ("自动驾驶", "autonomous_driving"),
    ("智驾", "autonomous_driving"), ("AV", "autonomous_driving"), ("大模型", "ai_infra"), ("ai_infra", "ai_infra"),
])
def test_sector_filter_takes_what_a_seeker_types(typed, sector):
    d = service.list_portals(typed)
    assert d["sector"] == sector and d["count"] >= 1
    assert all(p["sector"] == sector for p in d["portals"])


def test_an_unknown_sector_is_refused_with_the_choices():
    with pytest.raises(OpenHireError) as ei:
        service.list_portals("banking")
    assert ei.value.code == "ERR_BAD_SECTOR" and "embodied_ai" in ei.value.message
    assert service.list_portals("")["sector"] == "all"


def test_feishu_view_is_only_what_was_seen():
    """The Feishu line rests on one portal opened without logging in on 2026-10-15; it may
    say what was seen there (list, descriptions, no dates) and nothing about applying."""
    view = not_indexed.PORTAL_VIEW[not_indexed.FEISHU_ATS]
    assert "without logging in" in view and "no posting date" in view and "2026-10-15" in view
    assert "apply" not in view.lower()


def test_published_page_matches_the_registry():
    page = (ROOT / "docs" / "portals.html").read_text(encoding="utf-8")
    assert page == render(), "docs/portals.html is stale: run `ohp portals --html docs/portals.html`"
    assert EM_DASH not in page and "贵司" not in page and "小公司" not in page
    for p in service.list_portals()["portals"]:
        assert p["careers_url"] in page
    assert 'href="employers.html"' in page
    assert "已收录、但另有一个读不到的门户" in page and "k0fqxcszc9" in page


def test_cli_prints_json_and_writes_the_page(tmp_path):
    runner = CliRunner()
    res = runner.invoke(app, ["portals", "--sector", "具身", "--json"])
    assert res.exit_code == 0, res.output
    d = json.loads(res.output)
    assert d["sector"] == "embodied_ai" and d["count"] >= 10
    out = tmp_path / "portals.html"
    res = runner.invoke(app, ["portals", "--html", str(out)])
    assert res.exit_code == 0 and out.read_text(encoding="utf-8") == render()
    assert runner.invoke(app, ["portals", "--sector", "banking"]).exit_code == 2


def test_an_indexed_employer_with_a_second_portal_says_so_in_company_info(tmp_path, monkeypatch):
    """星动纪元 is read through its Moka board and also lists postings on Feishu: its
    company info carries the second portal, and an employer without one carries nothing."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from openhire.db.models import Base, Company

    eng = create_engine(f"sqlite:///{tmp_path / 'i.db'}")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Company(id="robotera", name="星动纪元 Robot Era", ats_vendor="moka", ats_tenant="robotera/163877"))
        s.add(Company(id="acme", name="Acme", ats_vendor="greenhouse", ats_tenant="acme"))
        s.commit()
        info = service.get_company_info(s, "robotera")
        assert [p["careers_url"] for p in info["also_posts_on"]] == ["https://k0fqxcszc9.jobs.feishu.cn/index"]
        assert "also_posts_on" not in service.get_company_info(s, "acme")
