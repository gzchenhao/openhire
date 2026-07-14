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
