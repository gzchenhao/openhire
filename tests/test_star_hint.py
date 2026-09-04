"""The star hint must be a one-time, value-triggered nudge — never a nag.

Design constraint (npm "terminal ads" episode → `npm fund`): unsolicited output on every
run gets a CLI banned from terminals. Locked down here:
  * shown once, only after a search that actually returned results;
  * never again on later runs (marker file);
  * never when there are no results (no value moment → no ask);
  * fully suppressible via OPENHIRE_NO_STAR_HINT=1;
  * `ohp star` is the opt-in, `npm fund`-style command and opens the repo URL.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select
from typer.testing import CliRunner

from openhire import cli, client
from openhire.cli import app
from openhire.db import Application, Company, Job, Watch, init_db, session_scope

runner = CliRunner()
UTC = dt.timezone.utc
HINT_MARK = "ohp star"  # the hint always mentions the opt-in command


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.delenv("OPENHIRE_NO_STAR_HINT", raising=False)
    init_db()
    with session_scope() as s:
        for t in (Application, Watch, Job, Company):
            for row in s.execute(select(t)).scalars():
                s.delete(row)
        s.flush()
        now = dt.datetime.now(UTC)
        s.add(Company(id="acme", name="Acme AI", ats_vendor="greenhouse", ats_tenant="acme",
                      careers_url="x", last_crawled_at=now))
        s.add(Job(
            id="acme:1", company_id="acme", title="Staff Rust Platform Engineer",
            description_raw="rust k8s " * 5, skills=["rust", "k8s"], remote_policy="remote",
            first_seen_at=now, verified_at=now, source="ats_public_api",
            apply_channel="https://boards.greenhouse.io/acme/jobs/1", content_hash="h1",
            ghost_score=0.0, extraction_source="deepseek",
        ))
    if client.star_hint_path().exists():
        client.star_hint_path().unlink()
    yield


def test_hint_shows_once_after_a_search_with_results():
    first = runner.invoke(app, ["search", "--skills", "rust"])
    assert first.exit_code == 0
    assert "1 条结果" in first.stdout
    assert HINT_MARK in first.stdout and cli.REPO_URL in first.stdout
    assert client.star_hint_path().exists()

    second = runner.invoke(app, ["search", "--skills", "rust"])
    assert second.exit_code == 0
    assert "1 条结果" in second.stdout
    assert HINT_MARK not in second.stdout  # one time means one time


def test_no_results_means_no_ask():
    res = runner.invoke(app, ["search", "--skills", "cobol"])
    assert res.exit_code == 0
    assert HINT_MARK not in res.stdout
    assert not client.star_hint_path().exists()


def test_env_opt_out_suppresses_and_leaves_no_marker(monkeypatch):
    monkeypatch.setenv("OPENHIRE_NO_STAR_HINT", "1")
    res = runner.invoke(app, ["search", "--skills", "rust"])
    assert res.exit_code == 0 and "1 条结果" in res.stdout
    assert HINT_MARK not in res.stdout
    assert not client.star_hint_path().exists()


def test_star_command_prints_url_and_opens_browser(monkeypatch):
    opened: list[str] = []
    monkeypatch.setattr(cli.webbrowser, "open", lambda url: opened.append(url) or True)
    res = runner.invoke(app, ["star"])
    assert res.exit_code == 0
    assert cli.REPO_URL in res.stdout
    assert opened == [cli.REPO_URL]


def test_star_command_no_open_never_touches_browser(monkeypatch):
    monkeypatch.setattr(cli.webbrowser, "open", lambda url: (_ for _ in ()).throw(AssertionError("must not open")))
    res = runner.invoke(app, ["star", "--no-open"])
    assert res.exit_code == 0
    assert cli.REPO_URL in res.stdout
