"""scripts/registry_state.py: the publish workflow's view of the MCP Registry.

Pinned: only this server's entries count (the search is a substring match); the four
exit codes mean what the workflow relies on (0 latest, 2 present, 1 absent, 3 unreadable),
so a mid-update index or a failed request is polled, never called a failed release.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("registry_state", ROOT / "scripts" / "registry_state.py")
rs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rs)


def _entry(name, version, latest=False):
    return {"server": {"name": name, "version": version}, "_meta": {rs.FLAG: {"isLatest": latest}}}


BODY = json.dumps({"servers": [
    _entry("io.github.gzchenhao/openhire", "0.8.7"),
    _entry("io.github.someone/openhire-fork", "9.9.9", latest=True),
    _entry("io.github.gzchenhao/openhire", "0.8.8", latest=True),
]})


def test_only_this_servers_entries_count_and_the_flag_is_read():
    assert rs.parse(BODY) == (["0.8.7", "0.8.8"], "0.8.8")
    assert rs.parse(json.dumps({"servers": []})) == ([], None)


def test_exit_codes_tell_latest_present_absent_and_unreadable_apart():
    assert rs.state("0.8.8", [(200, BODY)])[0] == 0
    assert rs.state("0.8.7", [(200, BODY)])[0] == 2, "in the registry, not flagged: published, poll for the flag"
    assert rs.state("0.8.9", [(200, BODY)])[0] == 1, "absent: the publish did not land"
    assert rs.state("0.8.8", [(429, "")])[0] == 3
    assert rs.state("0.8.8", [(0, "URLError: timeout")])[0] == 3
    assert rs.state("0.8.8", [(200, "<html>maintenance</html>")])[0] == 3
    unflagged = json.dumps({"servers": [_entry("io.github.gzchenhao/openhire", "0.8.8")]})
    assert rs.state("0.8.8", [(200, unflagged)])[0] == 2


def test_the_latest_version_on_the_second_page_is_found(monkeypatch):
    # 2026-10-14: 30 versions on page one, none flagged; 0.8.8 and the flag on page two.
    page1 = json.dumps({"servers": [_entry("io.github.gzchenhao/openhire", f"0.{i}.0") for i in range(30)],
                        "metadata": {"nextCursor": "c2", "count": 30}})
    page2 = json.dumps({"servers": [_entry("io.github.gzchenhao/openhire", "0.8.8", latest=True)], "metadata": {"count": 1}})
    seen = []

    def fake_read(url=rs.URL):
        seen.append(url)
        return (200, page2) if "cursor=c2" in url else (200, page1)

    monkeypatch.setattr(rs, "read", fake_read)
    pages = rs.read_pages()
    assert len(pages) == 2 and seen[1].endswith("&cursor=c2") and "limit=100" in seen[0]
    code, line = rs.state("0.8.8", pages)
    assert code == 0 and "pages=2" in line and "versions=31" in line
    assert rs.state("0.8.8", pages[:1])[0] == 1, "page one alone would call it absent: that was the bug"
    monkeypatch.setattr(rs, "read", lambda url=rs.URL: (0, "timeout"))
    assert rs.read_pages() == [(0, "timeout")]


def test_main_prints_one_line_and_returns_the_code(monkeypatch, capsys):
    monkeypatch.setattr(rs, "read", lambda url=rs.URL: (200, BODY))
    assert rs.main(["registry_state.py", "0.8.8"]) == 0
    out = capsys.readouterr().out.strip()
    assert out.startswith("want=0.8.8 http=200") and "present=True" in out and out.endswith("exit=0")
    assert rs.main(["registry_state.py"]) == 64
