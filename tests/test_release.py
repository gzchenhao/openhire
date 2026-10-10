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


def test_server_json_description_fits_the_registry():
    """registry.modelcontextprotocol.io rejects the publish with 422 above 100 characters,
    which is how the v0.6.2 tag published nothing until the description was cut."""
    data = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    assert len(data["description"]) <= 100, len(data["description"])

# --- plugin manifests (Claude Code + Cursor) carry the version too --------------------
def _json(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_plugin_manifests_match_pyproject():
    """Three more places since 2026-09-28: the Claude Code plugin manifest, the marketplace
    entry and the Cursor plugin manifest. A stale one would tell a plugin user they run an
    older server than `uvx openhire@latest` actually starts."""
    v = _declared()
    assert _json(".claude-plugin/plugin.json")["version"] == v
    entries = _json(".claude-plugin/marketplace.json")["plugins"]
    assert entries and all(e["version"] == v for e in entries)
    assert _json(".cursor-plugin/plugin.json")["version"] == v
    assert _json("plugin.json")["version"] == v, "the Agent Plugins (agent-plugins.org) manifest"


def test_plugin_mcp_configs_start_the_published_package():
    """Both plugin formats read a root mcp config; they must start the PyPI package, not a
    checkout, so a plugin install works on a machine that never cloned this repo."""
    for name in (".mcp.json", "mcp.json"):
        cfg = _json(name)["mcpServers"]["openhire"]
        assert cfg["command"] == "uvx" and cfg["args"] == [f"openhire=={_declared()}", "serve"], name


def test_uv_lock_pins_the_declared_version():
    """The Anthropic directory wants pyproject.toml + uv.lock at the plugin root for the
    Verified badge. A lock left over from before a version bump would pin the wrong
    release, so after bumping run `uv lock` and commit the result."""
    import re
    from pathlib import Path

    lock = (Path(__file__).resolve().parents[1] / "uv.lock").read_text(encoding="utf-8")
    m = re.search(r'^name = "openhire"\nversion = "([^"]+)"', lock, re.M)
    assert m, "uv.lock has no openhire entry; run `uv lock`"
    assert m.group(1) == _declared(), "uv.lock is stale; run `uv lock` after bumping the version"


def test_release_workflow_publishes_to_pypi_without_a_stored_token():
    """reports/066: PyPI goes through Trusted Publishing (OIDC), so a release can run from
    a cloud session or Actions with no token anywhere. A `password:` or a PyPI secret
    creeping back into the workflow would undo that."""
    wf = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "pypa/gh-action-pypi-publish" in wf
    assert "id-token: write" in wf
    assert "password:" not in wf
    assert "secrets." not in wf
    # reports/067: cloud sessions can push branches but not tags, so the release trigger is a
    # version change on main, and nothing is published unless the full suite is green first.
    assert "branches: [main]" in wf and "python -m pytest" in wf
    assert wf.index("python -m pytest") < wf.index("python -m build")
    reg = (ROOT / ".github" / "workflows" / "publish-mcp-registry.yml").read_text(encoding="utf-8")
    assert "workflow_run:" in reg and "workflows: [Release]" in reg and "tags:" not in reg
