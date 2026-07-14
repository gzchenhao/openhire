"""P0-1 regression: a concurrent reader must never block the watch_intent write path.

Under the default SQLite rollback journal, an open reader holds a SHARED lock that blocks
any writer; in the async stdio server that stalled write surfaced as a multi-minute hang.
The engine now opens SQLite in WAL mode with a busy timeout, so a writer proceeds while a
reader is active. These tests pin that behavior so it cannot silently regress.
"""

from __future__ import annotations

import datetime as dt
import threading
import time

import pytest
from sqlalchemy import select, text

from openhire import service
from openhire.db import Company, Job, Watch, get_engine, init_db, session_scope

UTC = dt.timezone.utc


def test_engine_is_wal_with_busy_timeout():
    init_db()
    with get_engine().connect() as c:
        assert c.exec_driver_sql("PRAGMA journal_mode").scalar().lower() == "wal"
        assert int(c.exec_driver_sql("PRAGMA busy_timeout").scalar()) > 0


@pytest.fixture()
def one_job():
    init_db()
    with session_scope() as s:
        for t in (Watch, Job, Company):
            for row in s.execute(select(t)).scalars():
                s.delete(row)
        s.flush()
        now = dt.datetime.now(UTC)
        s.add(Company(id="acme", name="Acme AI", ats_vendor="greenhouse",
                      ats_tenant="acme", careers_url="x", last_crawled_at=now))
        s.add(Job(id="acme:1", company_id="acme", title="Rust Infra", description_raw="x",
                  skills=["rust", "k8s"], remote_policy="remote", first_seen_at=now,
                  verified_at=now, source="ats_public_api", ghost_score=0.0,
                  apply_channel="https://boards.greenhouse.io/embed/job_app?for=acme&token=1",
                  content_hash="h1"))
    yield


def test_watch_write_not_blocked_by_open_reader(one_job):
    """Hold a real read transaction open, then time a watch_intent write in another thread."""
    reader_holding = threading.Event()
    reader_release = threading.Event()

    def reader():
        with session_scope() as s:
            # Open the read transaction and force it to acquire a lock, then hold it.
            s.execute(text("SELECT count(*) FROM jobs")).scalar()
            s.execute(text("SELECT id FROM jobs LIMIT 1")).scalar()
            reader_holding.set()
            reader_release.wait(timeout=15)

    th = threading.Thread(target=reader)
    th.start()
    assert reader_holding.wait(timeout=5)

    started = time.time()
    with session_scope() as s:
        out = service.watch_intent(
            s, "88ba1102edb9205d", {"skills": ["rust", "k8s"], "remote": True}
        )
    elapsed = time.time() - started
    reader_release.set()
    th.join()

    assert out["status"] == "active" and out["watch_id"].startswith("w_")
    # Must complete promptly — not stall on the busy timeout (the P0-1 symptom).
    assert elapsed < 2.0, f"watch_intent write blocked for {elapsed:.2f}s behind a reader"
