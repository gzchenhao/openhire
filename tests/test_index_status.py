"""index_status: while the first-start download runs, tools say "preparing", never "no jobs"
or "no index on this machine" (0.8.30, reports/100).

Tools wait up to 180 s for the download; past that they used to run on the still-empty
index. search_jobs then answered "no job index on this machine, run ohp bootstrap", and a
check_watches pull would have marked every watch notified on an empty index, after which the
whole snapshot would never be reported as new.
"""

from __future__ import annotations

import time

import pytest

from openhire import mcp_server as ms
from openhire.db import init_db


@pytest.fixture()
def preparing(monkeypatch):
    """The state during a first-start download: started, not ready, no error."""
    init_db()
    monkeypatch.setattr(ms, "_BOOTSTRAP_STARTED", True)
    monkeypatch.setattr(ms, "_INDEX_READY", ms.threading.Event())
    monkeypatch.setattr(ms, "_BOOTSTRAP_ERROR", None)
    monkeypatch.setattr(ms, "_BOOTSTRAP_STARTED_AT", time.monotonic() - 7)
    monkeypatch.setattr(ms, "_await_index", lambda timeout=180.0: None)  # the 180 s already passed
    yield


def test_search_and_company_and_apply_say_preparing(preparing):
    out = ms.search_jobs(skills=["perception"])
    assert out["index_status"] == "preparing" and out["results"] == [] and out["seconds_waited"] >= 7
    assert "not an empty market" in out["hint"] and "正在准备岗位数据" in out["hint"]
    assert out["headline"]["zh"] and out["headline"]["en"]
    assert "index_empty" not in out and "bootstrap_error" not in out
    assert ms.get_company_info("acme")["index_status"] == "preparing"
    assert ms.authorize_application("acme:1", "#prep-k2p7x8q1", True)["index_status"] == "preparing"


def test_check_watches_does_not_advance_markers_while_preparing(preparing):
    from sqlalchemy import select

    from openhire.db import Watch, session_scope

    saved = ms.watch_intent("#prep-watch-k2p7x8q1", {"skills": ["perception"]})
    assert saved["watch_id"].startswith("w_"), "a watch is still saved; it is carried into the new index"
    assert saved["index_status"] == "preparing" and saved["matching_now"] is None
    pulled = ms.check_watches("#prep-watch-k2p7x8q1")
    assert pulled["index_status"] == "preparing" and pulled["watches"] is None and pulled["results"] == []
    with session_scope() as s:
        w = s.execute(select(Watch).where(Watch.watch_id == saved["watch_id"])).scalar_one()
        assert w.last_notified_at is None, "a pull while preparing must not count as a notification"


def test_ready_means_no_status_and_failure_means_unavailable(monkeypatch):
    monkeypatch.setattr(ms, "_BOOTSTRAP_STARTED", True)
    ready = ms.threading.Event()
    ready.set()
    monkeypatch.setattr(ms, "_INDEX_READY", ready)
    assert ms._preparing() is None
    monkeypatch.setattr(ms, "_BOOTSTRAP_ERROR", "ConnectError: boom (url: x)")
    out = ms._explain_bootstrap_failure({"results": [], "index_empty": True, "hint": "old"})
    assert out["index_status"] == "unavailable" and out["bootstrap_error"].startswith("ConnectError")
    assert "连不上数据来源" in out["headline"]["zh"] and "network" in out["headline"]["en"]
    monkeypatch.setattr(ms, "_BOOTSTRAP_STARTED", False)
    assert ms._preparing() is None, "tools used without serve() never report preparing"
