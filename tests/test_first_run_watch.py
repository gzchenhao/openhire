"""A watch registered in the first session after auto-bootstrap works without a restart.

serve() creates every table (init_db) on the empty index file, then the bootstrap thread
replaces the whole file with the public snapshot, which carries companies and jobs only.
Until a restart ran init_db again, watch_intent and authorize_application failed with
"no such table: watches": a first-run tester hit exactly that ("设置盯岗又报错，重启后恢复",
reports/098), and the hosted endpoint, which bootstraps on every cold start because its
disk is not persistent, could never register a watch at all. _do_bootstrap now runs
init_db on the installed file.
"""

from __future__ import annotations

import datetime as dt
import sqlite3


def _public_snapshot(tmp_path, monkeypatch):
    """A snapshot built the way `ohp snapshot-build` publishes it: no user-state tables."""
    from openhire import config
    from openhire.db import init_db, session_scope
    from openhire.db.models import Company, Job
    from openhire.db.session import dispose_engine
    from openhire.pipeline.snapshot import build_snapshot

    src = tmp_path / "src.db"
    monkeypatch.setattr(config, "DATABASE_URL", f"sqlite:///{src.as_posix()}")
    dispose_engine()
    init_db()
    now = dt.datetime.now(dt.timezone.utc)
    with session_scope() as s:
        s.add(Company(id="acme", name="Acme Robotics", ats_vendor="greenhouse", ats_tenant="acme"))
        s.add(Job(
            id="acme:1", company_id="acme", title="Perception Engineer", skills=["perception"],
            first_seen_at=now, verified_at=now, posted_at=now, source="ats_public_api",
            apply_channel="https://job-boards.greenhouse.io/acme/jobs/1", content_hash="h1",
        ))
    dispose_engine()
    gz = tmp_path / "snap.db.gz"
    build_snapshot(str(src), str(gz))
    tables = {r[0] for r in sqlite3.connect(src).execute("select name from sqlite_master where type='table'")}
    assert {"watches", "applications"} <= tables, "the source index had the user-state tables"
    return gz


def test_watch_and_apply_work_in_the_first_session_after_bootstrap(tmp_path, monkeypatch, request):
    from openhire import config
    from openhire import mcp_server as ms
    from openhire.db import init_db
    from openhire.db.session import dispose_engine

    request.addfinalizer(dispose_engine)  # the next test must not inherit this engine
    gz = _public_snapshot(tmp_path, monkeypatch)

    # First run, in serve()'s order: init_db on the empty index, then the bootstrap thread
    # downloads the snapshot and replaces the file under it.
    user_db = tmp_path / "user.db"
    monkeypatch.setattr(config, "DATABASE_URL", f"sqlite:///{user_db.as_posix()}")
    monkeypatch.setattr(config, "SNAPSHOT_URL", gz.as_uri())
    monkeypatch.setattr(ms, "_BOOTSTRAP_STARTED", True)
    monkeypatch.setattr(ms, "_INDEX_READY", ms.threading.Event())
    monkeypatch.setattr(ms, "_BOOTSTRAP_ERROR", "not run yet")
    init_db()
    ms._do_bootstrap()
    assert ms._INDEX_READY.is_set()
    assert ms._BOOTSTRAP_ERROR is None, ms._BOOTSTRAP_ERROR
    tables = {r[0] for r in sqlite3.connect(user_db).execute("select name from sqlite_master where type='table'")}
    assert {"companies", "jobs", "watches", "applications"} <= tables, tables

    # The same process, no restart: the three tools a first session reaches for.
    fp = "#first-run-k2p7x8q1"
    rows = ms.search_jobs(skills=["perception"])
    assert isinstance(rows, list) and rows[0]["job_id"] == "acme:1"
    watch = ms.watch_intent(fp, {"skills": ["perception"]})
    assert watch.get("watch_id", "").startswith("w_"), watch
    pulled = ms.check_watches(fp)
    assert pulled["watches"] == 1 and pulled["new_matches"] == 1, pulled
    receipt = ms.authorize_application("acme:1", fp, True)
    assert receipt.get("receipt_id", "").startswith("r_"), receipt
    assert receipt["resume_transmitted"] is False


def test_a_watch_registered_during_the_download_survives_the_install(tmp_path, monkeypatch, request):
    """Tools stop waiting after 180 s; a watch written then lives in the empty file that the
    download is about to replace. install_snapshot(preserve_user_state=True) carries it over."""
    from openhire import config
    from openhire import mcp_server as ms
    from openhire.db import init_db
    from openhire.db.session import dispose_engine

    request.addfinalizer(dispose_engine)
    gz = _public_snapshot(tmp_path, monkeypatch)
    user_db = tmp_path / "user2.db"
    monkeypatch.setattr(config, "DATABASE_URL", f"sqlite:///{user_db.as_posix()}")
    monkeypatch.setattr(config, "SNAPSHOT_URL", gz.as_uri())
    monkeypatch.setattr(ms, "_BOOTSTRAP_STARTED", True)
    monkeypatch.setattr(ms, "_INDEX_READY", ms.threading.Event())
    monkeypatch.setattr(ms, "_BOOTSTRAP_ERROR", None)
    monkeypatch.setattr(ms, "_await_index", lambda timeout=180.0: None)
    init_db()
    saved = ms.watch_intent("#during-download-k2p7", {"skills": ["perception"]})
    assert saved["watch_id"].startswith("w_") and saved["index_status"] == "preparing"
    dispose_engine()
    ms._do_bootstrap()
    assert ms._BOOTSTRAP_ERROR is None
    pulled = ms.check_watches("#during-download-k2p7")
    assert pulled["watches"] == 1 and pulled["new_matches"] == 1
    assert pulled["results"][0]["watch_id"] == saved["watch_id"]
