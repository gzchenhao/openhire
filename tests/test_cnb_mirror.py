"""The CNB snapshot mirror (.cnb.yml, 0.8.17): its stage script against a mock of CNB's API.

Nothing on cnb.cool is reachable from where this repository is developed and tested, so the
pipeline that copies the weekly snapshot to a CNB Release cannot be tried for real before it
runs there. tests/cnb_mirror/ pulls the stage script out of the repository's own .cnb.yml,
runs it under dash and bash against mock_cnb.py (a local stand-in for api.cnb.cool, the
presigned storage and the GitHub asset), and checks: first run creates the release and
uploads; an unchanged snapshot is skipped without downloading it (ETag); a changed one
replaces the attachment; a truncated or non-SQLite file is refused; a fork skips; a relative
verify_url works; the token is never sent to storage or the public download.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent / "cnb_mirror"
TOOLS = ("bash", "curl", "jq", "gzip", "sha256sum", "timeout")


@pytest.mark.skipif(sys.platform == "win32", reason="the stage script is POSIX shell")
def test_snapshot_mirror_stage_against_a_mock_cnb(tmp_path):
    missing = [t for t in TOOLS if shutil.which(t) is None]
    if missing:
        pytest.skip(f"needs {', '.join(missing)}")
    pytest.importorskip("yaml")
    env = {"PATH": __import__("os").environ.get("PATH", ""), "PYTHON": sys.executable,
           "CNB_MOCK_PORT": "18766", "HOME": str(tmp_path)}
    out = subprocess.run(["bash", str(HERE / "run_tests.sh"), str(tmp_path / "data")],
                         capture_output=True, text=True, timeout=600, env=env)
    report = out.stdout + out.stderr
    assert out.returncode == 0 or "0 failed" in report, report
    assert "FAIL" not in report, report
    assert " 0 failed" in report, report
