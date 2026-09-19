"""`ohp doctor` — the checks that run where our server cannot.

The failure it exists for: a client never starts the server, so none of our hints, errors
or diagnoses execute. The terminal is the only channel left, which makes it the one place
a wrong answer is expensive — the user has nothing else to check it against.
"""

from __future__ import annotations

import json

import pytest

from openhire import doctor


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_finds_a_server_stored_per_project_not_at_the_top_level(tmp_path):
    """Claude Code keeps mcpServers under projects/<path>/. Reading only the top level
    reported "openhire is not configured" for a client where it plainly was."""
    p = _write(tmp_path / ".claude.json", {
        "numStartups": 12,
        "projects": {
            "C:/work/thing": {"mcpServers": {}},
            "C:/openhire": {"mcpServers": {
                "openhire": {"command": "uvx", "args": ["openhire@latest", "serve"]}
            }},
        },
    })
    assert doctor.find_openhire(p) == ("openhire", "uvx openhire@latest serve")


def test_reads_the_vs_code_spelling_too(tmp_path):
    p = _write(tmp_path / "mcp.json",
               {"servers": {"oh": {"command": "uvx", "args": ["openhire", "serve"]}}})
    assert doctor.find_openhire(p) is not None


def test_a_config_without_us_is_not_a_false_positive(tmp_path):
    p = _write(tmp_path / "mcp.json",
               {"mcpServers": {"other": {"command": "npx", "args": ["some-server"]}}})
    assert doctor.find_openhire(p) is None


def test_unreadable_or_missing_config_is_not_a_crash(tmp_path):
    assert doctor.find_openhire(tmp_path / "nope.json") is None
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert doctor.find_openhire(broken) is None


@pytest.fixture()
def fake_home(tmp_path, monkeypatch):
    """A home directory with only a Cursor config, so the check set is predictable."""
    monkeypatch.setattr(doctor, "known_client_configs", lambda home=None: [
        doctor.ClientConfig("Cursor", tmp_path / ".cursor" / "mcp.json", True),
        doctor.ClientConfig("Windsurf", tmp_path / ".codeium" / "mcp.json", False),
    ])
    return tmp_path


def test_missing_uvx_is_only_a_failure_when_a_config_actually_uses_it(fake_home, monkeypatch):
    """The maintainer's own machine has no uvx and works fine: its config points at an
    installed `ohp`. Calling that a failure sends someone to fix a prerequisite they do
    not have and do not need."""
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)

    _write(fake_home / ".cursor" / "mcp.json",
           {"mcpServers": {"openhire": {"command": "C:/openhire/.venv/Scripts/ohp.exe",
                                        "args": ["serve"]}}})
    levels = {f.level for f in doctor.run_checks() if "uvx" in f.text}
    assert levels == {"ok"}, "an ohp-based config must not be told to install uv"

    _write(fake_home / ".cursor" / "mcp.json",
           {"mcpServers": {"openhire": {"command": "uvx", "args": ["openhire@latest", "serve"]}}})
    fails = [f for f in doctor.run_checks() if f.level == "fail" and "uvx" in f.text]
    assert fails and fails[0].action, "a uvx-based config with no uvx must say how to fix it"


def test_a_client_that_gates_new_servers_is_called_out(fake_home, monkeypatch):
    """The switch we cannot read is the one that bites. We must name the gate without
    claiming to know whether it is on."""
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/usr/bin/uvx")
    _write(fake_home / ".cursor" / "mcp.json",
           {"mcpServers": {"openhire": {"command": "uvx", "args": ["openhire@latest", "serve"]}}})

    texts = [f.text for f in doctor.run_checks()]
    gate = [t for t in texts if "启用" in t]
    assert gate, "a gated client must produce an enable-it note"
    # And it must not assert the switch's state, which we cannot see.
    assert any("读不到" in t for t in gate)


def test_other_clients_lacking_openhire_are_not_chores_when_one_has_it(fake_home, monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/usr/bin/uvx")
    _write(fake_home / ".cursor" / "mcp.json",
           {"mcpServers": {"openhire": {"command": "uvx", "args": ["openhire", "serve"]}}})
    _write(fake_home / ".codeium" / "mcp.json", {"mcpServers": {}})

    findings = doctor.run_checks()
    about_windsurf = [f for f in findings if "Windsurf" in f.text]
    assert about_windsurf and all(f.level == "ok" for f in about_windsurf)
    assert all(f.action is None for f in about_windsurf), "no chores for an unrelated client"
