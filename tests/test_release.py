"""Every place a release version is written must agree with pyproject.toml.

Five locations, and history says each one has drifted at least once:
  - server.json (twice: top-level and the PyPI package entry) -> MCP Registry
  - mcpb/manifest.json -> what Claude Desktop shows
  - mcpb/pyproject.toml -> what the .mcpb ACTUALLY INSTALLS (`uv run` resolves it from PyPI)
  - README.md -> the .mcpb filename users are told to download

The last one is the worst: v0.6.1's bundle carried manifest 0.6.1 but pinned
`openhire==0.5.1`, so every double-click install ran 0.5.1 while the release notes said
the crash was fixed. A bump is a five-file edit, and this test is the checklist.
"""
from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _declared() -> str:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def test_server_json_versions_match_pyproject():
    data = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    v = _declared()
    assert data["version"] == v, f"server.json top-level version {data['version']} != {v}"
    for pkg in data["packages"]:
        assert pkg["version"] == v, f"server.json package version {pkg['version']} != {v}"


def test_mcpb_manifest_version_matches_pyproject():
    data = json.loads((ROOT / "mcpb" / "manifest.json").read_text(encoding="utf-8"))
    assert data["version"] == _declared()


def test_mcpb_wrapper_installs_the_same_version_it_claims():
    """The bundle's own pyproject is what `uv run` resolves; the manifest is just a label."""
    wrapper = tomllib.loads((ROOT / "mcpb" / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    v = _declared()
    assert wrapper["version"] == v, f"mcpb/pyproject.toml version {wrapper['version']} != {v}"
    pins = [d for d in wrapper["dependencies"] if d.startswith("openhire")]
    assert pins == [f"openhire=={v}"], (
        f"mcpb/pyproject.toml pins {pins}; a double-click install would run that, not {v}"
    )


def test_readme_names_the_current_mcpb():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    v = _declared()
    named = set(re.findall(r"openhire-(\d+\.\d+\.\d+)\.mcpb", readme))
    assert named == {v}, f"README names .mcpb versions {sorted(named)}, pyproject says {v}"
    pinned = set(re.findall(r'"openhire==(\d+\.\d+\.\d+)"', readme))
    assert pinned <= {v}, f"README pins openhire=={sorted(pinned)}, pyproject says {v}"
