"""The domestic mirror for the snapshot (0.8.17): when the default GitHub source fails, the CNB
copy is tried under the same checks; a URL the user chose is used alone.

The maintainer approved a mainland-China mirror on 2026-10-21. A Kimi sandbox in mainland
China gave up at 20 MB of the GitHub asset (reports/055) and left an empty index; the CNB
copy is refreshed from GitHub every 6 hours by .cnb.yml (tests/test_cnb_mirror.py).
"""
from __future__ import annotations

import shutil

import pytest

from openhire import config
from openhire.pipeline import snapshot as snap

from test_snapshot import _public_snapshot

GITHUB = config.DEFAULT_SNAPSHOT_URL
CNB = "https://cnb.cool/gzchenhao/openhire/-/releases/download/snapshot/openhire-index.db.gz"


def _fake_fetch(served: dict, calls: list):
    """_fetch_to stand-in: copy the file served for a URL, or raise what is registered."""
    def fetch(url, dest, attempts=snap.FETCH_ATTEMPTS):
        calls.append((url, attempts))
        what = served[url]
        if isinstance(what, Exception):
            raise what
        shutil.copyfile(what, dest)
    return fetch


def test_the_cnb_copy_is_the_default_mirror_and_only_for_the_default_source(monkeypatch):
    assert CNB in config.SNAPSHOT_MIRRORS
    assert snap.mirrors_for(GITHUB) == config.SNAPSHOT_MIRRORS
    assert snap.mirrors_for("https://mirror.example.org/openhire-index.db.gz") == ()
    assert snap.mirrors_for("C:/Users/me/openhire-index.db.gz") == ()


def test_github_failing_falls_back_to_the_mirror(tmp_path, monkeypatch):
    import httpx

    gz = _public_snapshot(tmp_path)
    calls: list = []
    monkeypatch.setattr(snap, "_fetch_to", _fake_fetch(
        {GITHUB: httpx.ReadTimeout("stalled at 20 MB"), CNB: gz}, calls))
    res = snap.download_snapshot(GITHUB, tmp_path / "out.db", mirrors=(CNB,))
    assert res.jobs == 1 and res.source == CNB
    assert calls == [(GITHUB, 2), (CNB, snap.FETCH_ATTEMPTS)], "GitHub hands over after two attempts"


def test_github_answering_needs_no_mirror(tmp_path, monkeypatch):
    gz = _public_snapshot(tmp_path)
    calls: list = []
    monkeypatch.setattr(snap, "_fetch_to", _fake_fetch({GITHUB: gz, CNB: RuntimeError("unused")}, calls))
    res = snap.download_snapshot(GITHUB, tmp_path / "out.db", mirrors=(CNB,))
    assert res.source == GITHUB and [u for u, _ in calls] == [GITHUB]


def test_a_mirror_is_held_to_the_same_checks(tmp_path, monkeypatch):
    """A copy that is not a valid public-only snapshot is refused like any other."""
    import gzip

    import httpx

    bad = tmp_path / "not-a-snapshot.db.gz"
    with gzip.open(bad, "wb") as f:
        f.write(b"definitely not sqlite " * 100)
    monkeypatch.setattr(snap, "_fetch_to", _fake_fetch(
        {GITHUB: httpx.ConnectTimeout("blocked"), CNB: bad}, []))
    with pytest.raises(snap.SnapshotError) as ei:
        snap.download_snapshot(GITHUB, tmp_path / "out.db", mirrors=(CNB,))
    assert "github.com" in str(ei.value) and "cnb.cool" in str(ei.value)
    assert not (tmp_path / "out.db").exists()


def test_a_url_the_user_chose_is_used_alone(tmp_path, monkeypatch):
    import httpx

    calls: list = []
    mine = "https://mirror.example.org/openhire-index.db.gz"
    monkeypatch.setattr(snap, "_fetch_to", _fake_fetch({mine: httpx.ConnectTimeout("down")}, calls))
    with pytest.raises(httpx.ConnectTimeout):
        snap.download_snapshot(mine, tmp_path / "out.db")
    assert calls == [(mine, snap.FETCH_ATTEMPTS)]


def test_install_reports_which_source_it_used(tmp_path, monkeypatch):
    import httpx

    gz = _public_snapshot(tmp_path)
    monkeypatch.setattr(config, "SNAPSHOT_MIRRORS", (CNB,))
    monkeypatch.setattr(snap, "_fetch_to", _fake_fetch({GITHUB: httpx.ConnectError("refused"), CNB: gz}, []))
    res = snap.install_snapshot(GITHUB, str(tmp_path / "live.db"))
    assert res.source == CNB and (tmp_path / "live.db").exists()
