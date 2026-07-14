"""End-to-end M3 journey via the real CLI (Typer CliRunner) on the temp DB/home.

Covers: init → watch → check (baseline) → new JD lands → check (increment) → apply
(receipt) → status, plus the unknown-job error path.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select
from typer.testing import CliRunner

from openhire import client
from openhire.cli import app
from openhire.db import Application, Company, Job, Watch, init_db, session_scope

runner = CliRunner()
UTC = dt.timezone.utc


def _mkjob(jid, cid, title, skills, remote, when, salary=None):
    smin, smax, cur = salary if salary else (None, None, None)
    return Job(
        id=f"{cid}:{jid}", company_id=cid, title=title, description_raw=title * 3,
        skills=skills, remote_policy=remote, salary_min=smin, salary_max=smax,
        salary_currency=cur, first_seen_at=when, verified_at=when, source="ats_public_api",
        apply_channel=f"https://boards.greenhouse.io/embed/job_app?for={cid}&token={jid}",
        content_hash=f"h{jid}", ghost_score=0.0, extraction_source="deepseek",
    )


@pytest.fixture(autouse=True)
def fresh(tmp_path):
    init_db()
    with session_scope() as s:
        for t in (Application, Watch, Job, Company):
            for row in s.execute(select(t)).scalars():
                s.delete(row)
        s.flush()
        now = dt.datetime.now(UTC)
        s.add(Company(id="acme", name="Acme AI", ats_vendor="greenhouse", ats_tenant="acme",
                      careers_url="x", last_crawled_at=now))
        s.add(_mkjob("1", "acme", "Staff Rust Platform Engineer",
                     ["rust", "k8s"], "remote", now, salary=(700000, 900000, "USD")))
    for p in (client.fingerprint_path(), client.receipts_path()):
        if p.exists():
            p.unlink()
    yield


def test_init_scan_creates_fingerprint(tmp_path):
    repo = tmp_path / "proj"
    (repo / "s").mkdir(parents=True)
    (repo / "s" / "main.rs").write_text("fn main(){}", encoding="utf-8")
    res = runner.invoke(app, ["init", "--scan", str(repo), "--yes"])
    assert res.exit_code == 0
    fp = client.load_fingerprint()
    assert fp is not None and "rust" in fp.skills


def test_full_watch_check_apply_journey():
    # watch (auto-creates an anonymous fingerprint)
    r = runner.invoke(app, ["watch", "--skills", "rust", "--remote"])
    assert r.exit_code == 0
    with session_scope() as s:
        assert s.execute(select(Watch)).scalars().first() is not None

    # baseline check consumes the current match, advancing the marker
    r = runner.invoke(app, ["check"])
    assert r.exit_code == 0

    # a NEW matching JD lands later (as if from a fresh crawl)
    with session_scope() as s:
        later = dt.datetime.now(UTC) + dt.timedelta(seconds=1)
        s.add(_mkjob("77", "acme", "Senior Rust Infra Engineer", ["rust"], "remote", later))

    # check now returns the increment
    r = runner.invoke(app, ["check"])
    assert r.exit_code == 0
    assert "Senior Rust Infra Engineer" in r.stdout  # the new hit surfaced

    # apply to the new job → receipt recorded, no résumé transmitted
    r = runner.invoke(app, ["apply", "acme:77", "--yes", "--no-open"])
    assert r.exit_code == 0
    receipts = client.load_receipts()
    assert len(receipts) == 1
    assert receipts[0]["job_id"] == "acme:77"
    assert receipts[0]["resume_transmitted"] is False
    # An Application row exists server-side, authorized, no PII beyond the fingerprint.
    with session_scope() as s:
        app_row = s.execute(select(Application)).scalars().one()
        assert app_row.authorized is True and app_row.delivered_via == "employer_site"


def test_apply_shows_summary_before_authorizing():
    r = runner.invoke(app, ["apply", "acme:1", "--yes", "--no-open"])
    assert r.exit_code == 0
    # JD summary (company/title/salary) is printed before the success line.
    assert "Acme AI" in r.stdout
    assert "Staff Rust Platform Engineer" in r.stdout
    assert "已直达雇主 ATS" in r.stdout


def test_apply_unknown_job_errors():
    # The ERR_ code is written to stderr (errors belong there); the exit code signals it.
    r = runner.invoke(app, ["apply", "acme:doesnotexist", "--yes", "--no-open"])
    assert r.exit_code == 1


def test_status_shows_identity_and_receipts():
    runner.invoke(app, ["watch", "--skills", "rust", "--remote"])
    runner.invoke(app, ["apply", "acme:1", "--yes", "--no-open"])
    r = runner.invoke(app, ["status"])
    assert r.exit_code == 0
    assert "w_" in r.stdout        # watch listed
    assert "r_" in r.stdout        # receipt listed
