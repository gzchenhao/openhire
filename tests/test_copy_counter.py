"""The connect guide's anonymous copy counter (leader approved 2026-11-12, reports/145)."""
import datetime as dt
import json
import re
from pathlib import Path

from openhire import hosted

ROOT = Path(__file__).resolve().parents[1]


def test_counts_only_known_assistants_per_day(tmp_path, monkeypatch):
    from openhire import config
    monkeypatch.setattr(config, "CLIENT_HOME", tmp_path)
    day = dt.date(2026, 11, 12)
    assert hosted.count_copy("chatgpt", day) and hosted.count_copy("chatgpt", day)
    assert hosted.count_copy("doubao", day)
    assert not hosted.count_copy("x" * 500, day), "unknown names are dropped, never stored"
    assert not hosted.count_copy(None, day)
    stored = json.loads((tmp_path / "copy_counts.json").read_text(encoding="utf-8"))
    assert stored == {"2026-11-12": {"chatgpt": 2, "doubao": 1}}
    assert hosted.copy_counts() == stored


def test_the_page_sends_nothing_but_the_assistant_name():
    page = (ROOT / "docs" / "connect.html").read_text(encoding="utf-8")
    beacons = re.findall(r'sendBeacon\(([^;]*)\)', page)
    assert beacons == ['"https://openhire-vlny.onrender.com/c/copy?k="+encodeURIComponent(k)']
    assert "document.cookie" not in page and "localStorage.setItem(\"oh_id" not in page
    assert "不记任何个人信息" in page and "nothing about you" in page


def test_privacy_notice_says_so():
    text = (ROOT / "docs" / "PRIVACY.md").read_text(encoding="utf-8")
    assert "One anonymous counter" in text and "/c/counts" in text
