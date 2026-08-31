"""`ohp ingest --fail-over N` — a broken crawl must not look like a success.

The weekly snapshot refresh runs unattended in CI with nobody reading the log. Without a
non-zero exit, a run where most boards 404 would sail through and publish a gutted index.
`--fail-over` turns that into a job failure (and therefore GitHub's failure email), while
leaving the default interactive behaviour untouched.
"""

from __future__ import annotations

from typer.testing import CliRunner

from openhire.cli import app
from openhire.pipeline.ingest import IngestStats

runner = CliRunner()


def _stub_ingest(monkeypatch, failed: int):
    stats = IngestStats(
        companies_crawled=125 - failed,
        companies_failed=failed,
        failed_tenants=[f"greenhouse:dead{i}" for i in range(failed)],
        jobs_new=1,
    )
    import openhire.pipeline as pipeline

    monkeypatch.setattr(pipeline, "run_ingest", lambda **kw: stats)
    return stats


def test_ingest_exits_zero_when_failures_are_under_the_threshold(monkeypatch):
    _stub_ingest(monkeypatch, failed=3)
    res = runner.invoke(app, ["ingest", "--all", "--fail-over", "10"])
    assert res.exit_code == 0


def test_ingest_exits_nonzero_when_too_many_boards_fail(monkeypatch):
    _stub_ingest(monkeypatch, failed=42)
    res = runner.invoke(app, ["ingest", "--all", "--fail-over", "10"])
    assert res.exit_code == 1
    assert "ERR_INGEST_TOO_MANY_FAILURES" in res.output


def test_ingest_at_exactly_the_threshold_still_passes(monkeypatch):
    # "more than N", not "N or more" — 10 failures out of 125 is tolerable drift.
    _stub_ingest(monkeypatch, failed=10)
    res = runner.invoke(app, ["ingest", "--all", "--fail-over", "10"])
    assert res.exit_code == 0


def test_ingest_without_the_flag_never_fails_on_crawl_errors(monkeypatch):
    # The interactive default is unchanged: a human can see the failures listed.
    _stub_ingest(monkeypatch, failed=99)
    res = runner.invoke(app, ["ingest", "--all"])
    assert res.exit_code == 0
