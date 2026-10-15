"""Snapshot red line: a published snapshot carries ONLY public jobs/companies — ZERO
user-state (watches/applications), enforced at build time. Plus a build→install round-trip.
"""

from __future__ import annotations

import datetime as dt
import gzip
import sqlite3

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from openhire.db.models import Application, Base, Company, Job, Watch
from openhire.pipeline.snapshot import (
    SnapshotError,
    build_snapshot,
    install_snapshot,
    _USER_STATE_TABLES,
)

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 7, 12, tzinfo=UTC)


def _seed_source(path) -> None:
    """A source DB that DOES contain user-state, to prove the build strips it out."""
    engine = create_engine(f"sqlite+pysqlite:///{path.as_posix()}", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        s.add(Company(id="acme", name="Acme AI", ats_vendor="greenhouse", ats_tenant="acme",
                      careers_url="x", last_crawled_at=NOW))
        s.add(Job(id="acme:1", company_id="acme", title="Rust Infra", description_raw="x",
                  skills=["rust"], remote_policy="remote", first_seen_at=NOW,
                  verified_at=NOW - dt.timedelta(days=3), source="ats_public_api",
                  ghost_score=0.0, role_family="engineering",
                  apply_channel="https://boards.greenhouse.io/embed/job_app?for=acme&token=1",
                  content_hash="h1"))
        # USER STATE — must never reach the snapshot:
        s.add(Watch(watch_id="w_1", fingerprint="#a3f9", filters={"skills": ["rust"]},
                    created_at=NOW, active=True))
        s.add(Application(receipt_id="r_1", job_id="acme:1", fingerprint="#a3f9",
                          authorized=True, delivered_via="employer_site", created_at=NOW))
        s.commit()
    engine.dispose()


def test_snapshot_strips_all_user_state(tmp_path):
    src = tmp_path / "source.db"
    _seed_source(src)
    out = tmp_path / "snap.db.gz"

    res = build_snapshot(str(src), str(out))
    assert res.jobs == 1 and res.companies == 1
    assert out.exists()

    # Decompress and inspect the actual snapshot contents.
    raw = tmp_path / "snap.db"
    with gzip.open(out, "rb") as f_in, open(raw, "wb") as f_out:
        f_out.write(f_in.read())
    conn = sqlite3.connect(raw)
    try:
        assert conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM companies").fetchone()[0] == 1
        for t in _USER_STATE_TABLES:
            # User-state tables must be absent entirely (or, if present, empty).
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)
            ).fetchone()
            n = conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] if exists else 0
            assert n == 0, f"{t} leaked into the snapshot"
    finally:
        conn.close()


def test_build_refuses_empty_index(tmp_path):
    src = tmp_path / "empty.db"
    engine = create_engine(f"sqlite+pysqlite:///{src.as_posix()}", future=True)
    Base.metadata.create_all(engine)
    engine.dispose()
    with pytest.raises(SnapshotError):
        build_snapshot(str(src), str(tmp_path / "x.db.gz"))


def test_install_rejects_snapshot_with_user_state(tmp_path):
    # Craft a "snapshot" that illegally contains a watch row; install must refuse it.
    bad = tmp_path / "bad.db"
    engine = create_engine(f"sqlite+pysqlite:///{bad.as_posix()}", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        s.add(Company(id="acme", name="Acme", ats_vendor="greenhouse", ats_tenant="acme",
                      careers_url="x", last_crawled_at=NOW))
        s.add(Job(id="acme:1", company_id="acme", title="T", description_raw="x", skills=["rust"],
                  remote_policy="remote", first_seen_at=NOW, verified_at=NOW,
                  source="ats_public_api", ghost_score=0.0, apply_channel="https://x/1",
                  content_hash="h"))
        s.add(Watch(watch_id="w_1", fingerprint="#a3f9", filters={}, created_at=NOW, active=True))
        s.commit()
    engine.dispose()
    bad_gz = tmp_path / "bad.db.gz"
    with open(bad, "rb") as f_in, gzip.open(bad_gz, "wb") as f_out:
        f_out.write(f_in.read())

    with pytest.raises(SnapshotError):
        install_snapshot(str(bad_gz), str(tmp_path / "target.db"))


def test_build_then_install_roundtrip(tmp_path):
    src = tmp_path / "source.db"
    _seed_source(src)
    gz = tmp_path / "snap.db.gz"
    build_snapshot(str(src), str(gz))

    target = tmp_path / "installed.db"
    res = install_snapshot(str(gz), str(target))
    assert res.jobs == 1 and res.companies == 1
    assert res.age_days is not None and res.age_days >= 3  # verified_at was 3 days old
    conn = sqlite3.connect(target)
    try:
        # The installed image carries no user-state table (the app re-creates it on use).
        assert conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='watches'"
        ).fetchone()[0] == 0
        assert conn.execute("SELECT role_family FROM jobs WHERE id='acme:1'").fetchone()[0] == "engineering"
    finally:
        conn.close()


# --- staging, activation and user-state carry-over (0.8.11) ----------------------------
def _gz_of(db_path, gz_path) -> None:
    with open(db_path, "rb") as f_in, gzip.open(gz_path, "wb") as f_out:
        f_out.write(f_in.read())


def _public_snapshot(tmp_path, job_id="acme:2", title="Perception Engineer"):
    """A valid public-only snapshot (one company, one job, empty user tables), gzipped."""
    from openhire.pipeline.snapshot import build_snapshot

    src = tmp_path / "pub-src.db"
    engine = create_engine(f"sqlite+pysqlite:///{src.as_posix()}", future=True)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as s:
        s.add(Company(id="acme", name="Acme AI", ats_vendor="greenhouse", ats_tenant="acme",
                      careers_url="x", last_crawled_at=NOW))
        s.add(Job(id=job_id, company_id="acme", title=title, description_raw="x",
                  skills=["c++"], remote_policy="remote", first_seen_at=NOW,
                  verified_at=NOW, source="ats_public_api", ghost_score=0.0,
                  role_family="engineering",
                  apply_channel="https://boards.greenhouse.io/embed/job_app?for=acme&token=2",
                  content_hash="h2"))
        s.commit()
    engine.dispose()
    gz = tmp_path / "pub.db.gz"
    build_snapshot(str(src), str(gz))
    return gz


def test_stage_then_activate_carries_watches_into_the_new_index(tmp_path):
    """The hosted refresh and `ohp bootstrap --force` both go through this path: the new
    snapshot waits next to the live file, activation swaps the files, and the old file's
    watches and application records (anonymous fingerprint + filters, no PII) end up in
    the new index. Losing them on every refresh was the 0.8.4 roadmap item."""
    from openhire.pipeline.snapshot import (
        activate_staged, carry_over_user_state, stage_snapshot, staged_path,
    )

    live = tmp_path / "openhire.db"
    _seed_source(live)  # old index: one job, one watch, one application record
    gz = _public_snapshot(tmp_path)

    res = stage_snapshot(gz.as_uri(), live)
    assert res.jobs == 1 and staged_path(live).exists()
    # Staging touched nothing live:
    with sqlite3.connect(live) as c:
        assert c.execute("SELECT count(*) FROM watches").fetchone()[0] == 1
        assert c.execute("SELECT id FROM jobs").fetchone()[0] == "acme:1"

    previous = activate_staged(live)
    assert previous is not None and previous.exists() and not staged_path(live).exists()
    copied = carry_over_user_state(previous, live)
    assert copied == {"watches": 1, "applications": 1}
    with sqlite3.connect(live) as c:
        assert [r[0] for r in c.execute("SELECT id FROM jobs")] == ["acme:2"]  # the new snapshot
        assert c.execute("SELECT fingerprint FROM watches").fetchone()[0] == "#a3f9"
        assert c.execute("SELECT receipt_id FROM applications").fetchone()[0] == "r_1"
    # Carry-over is idempotent (INSERT OR IGNORE on the primary keys):
    assert carry_over_user_state(previous, live) == {"watches": 0, "applications": 0}


def test_activate_with_nothing_staged_is_a_noop(tmp_path):
    from openhire.pipeline.snapshot import activate_staged

    live = tmp_path / "openhire.db"
    _seed_source(live)
    assert activate_staged(live) is None
    with sqlite3.connect(live) as c:
        assert c.execute("SELECT count(*) FROM watches").fetchone()[0] == 1


def test_install_snapshot_keeps_user_state_only_when_asked(tmp_path):
    from openhire.pipeline.snapshot import install_snapshot

    gz = _public_snapshot(tmp_path)
    live = tmp_path / "openhire.db"
    _seed_source(live)
    install_snapshot(gz.as_uri(), str(live))  # the old contract: a plain overwrite
    with sqlite3.connect(live) as c:
        has_table = c.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='watches'"
        ).fetchone()[0]
        assert not has_table or c.execute("SELECT count(*) FROM watches").fetchone()[0] == 0

    _seed_source(tmp_path / "again.db")
    live2 = tmp_path / "again.db"
    install_snapshot(gz.as_uri(), str(live2), preserve_user_state=True)
    with sqlite3.connect(live2) as c:
        assert c.execute("SELECT count(*) FROM watches").fetchone()[0] == 1
        assert [r[0] for r in c.execute("SELECT id FROM jobs")] == ["acme:2"]
    assert not (tmp_path / "again.db.previous").exists()
    assert not (tmp_path / "again.db.staged").exists()


def test_staging_rejects_a_snapshot_with_user_state_and_leaves_nothing_behind(tmp_path):
    from openhire.pipeline.snapshot import SnapshotError, stage_snapshot, staged_path

    bad = tmp_path / "bad.db"
    _seed_source(bad)  # has watches: must be refused
    bad_gz = tmp_path / "bad.db.gz"
    _gz_of(bad, bad_gz)
    live = tmp_path / "openhire.db"
    with pytest.raises(SnapshotError):
        stage_snapshot(bad_gz.as_uri(), live)
    assert not staged_path(live).exists()
    assert not list(tmp_path.glob("openhire.db.staged*"))


def test_snapshot_fingerprint_changes_with_a_local_file(tmp_path):
    from openhire.pipeline.snapshot import snapshot_fingerprint

    f = tmp_path / "snap.db.gz"
    f.write_bytes(b"one")
    a = snapshot_fingerprint(f.as_uri())
    assert a and a.startswith("3:")
    f.write_bytes(b"longer")
    assert snapshot_fingerprint(f.as_uri()) != a
    assert snapshot_fingerprint((tmp_path / "missing").as_uri()) is None
