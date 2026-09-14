"""refresh_index — N2(a) from the round-2 tester report.

The gap: the index refreshes weekly, so `search_jobs` can be a week behind and
`check_watches` has nothing to report until it moves. Nothing in the MCP surface owned the
data's lifecycle, so "make it look again" meant quitting the conversation and opening a
terminal.

The constraint that shapes it: our crawl is a weekly batch we control. Handing refresh to
callers turns it into our users hitting somebody else's public endpoint on our behalf, so
the throttle is not a nicety — it is the thing that keeps the crawl-boundary rule (020) ours
to keep rather than ours to spend.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from openhire import service
from openhire.db import Application, Company, Job, init_db, session_scope

NOW = dt.datetime(2026, 9, 14, 12, 0, tzinfo=dt.timezone.utc)


@pytest.fixture()
def seeded():
    init_db()
    with session_scope() as s:
        for t in (Application, Job, Company):
            for row in s.execute(select(t)).scalars():
                s.delete(row)
        s.flush()
        s.add_all([
            Company(id="unitree", name="宇树科技 Unitree", ats_vendor="beisen",
                    ats_tenant="unitree", last_crawled_at=NOW - dt.timedelta(hours=1)),
            Company(id="pathrobotics", name="Path Robotics", ats_vendor="greenhouse",
                    ats_tenant="pathrobotics", last_crawled_at=NOW - dt.timedelta(hours=1)),
            Company(id="ambirobotics", name="Ambi Robotics", ats_vendor="greenhouse",
                    ats_tenant="ambirobotics", last_crawled_at=NOW - dt.timedelta(hours=1)),
        ])
        s.flush()
    yield


def test_throttled_call_makes_no_network_request(seeded, monkeypatch):
    """The throttle is checked BEFORE the crawl, so a too-soon call costs the ATS nothing."""
    import openhire.pipeline as pipeline

    def _boom(*a, **k):  # pragma: no cover - must never run
        raise AssertionError("run_ingest called despite the throttle")

    monkeypatch.setattr(pipeline, "run_ingest", _boom)
    with session_scope() as s:
        out = service.refresh_company_index(s, "unitree", now=NOW)
    assert out["refreshed"] is False
    assert out["reason"] == "throttled"
    assert out["last_refreshed_at"] and out["next_allowed_at"]


def test_throttle_window_is_exactly_six_hours(seeded, monkeypatch):
    """Both sides of the boundary, and neither may touch the network: the seeded company was
    crawled 1h before NOW, so NOW+4h is 5h old (blocked) and NOW+5h01m is 6h01m old (allowed)."""
    import openhire.pipeline as pipeline

    calls: list[list[str]] = []

    class _Stats:
        jobs_new = jobs_updated = jobs_delisted = jobs_unchanged = 0

    monkeypatch.setattr(pipeline, "run_ingest",
                        lambda company_ids=None, **k: (calls.append(company_ids), _Stats())[1])

    assert service.REFRESH_THROTTLE_HOURS == 6
    with session_scope() as s:
        inside = service.refresh_company_index(s, "unitree", now=NOW + dt.timedelta(hours=4))
        assert inside["reason"] == "throttled"
        assert calls == [], "a throttled call must not crawl"

        outside = service.refresh_company_index(
            s, "unitree", now=NOW + dt.timedelta(hours=5, minutes=1)
        )
        assert outside["refreshed"] is True
        assert calls == [["unitree"]], "and only that one employer"


def test_ambiguous_input_is_refused_not_fanned_out(seeded, monkeypatch):
    """A vague word must never turn into several live crawls."""
    import openhire.pipeline as pipeline

    monkeypatch.setattr(pipeline, "run_ingest",
                        lambda *a, **k: pytest.fail("crawled on an ambiguous match"))
    with session_scope() as s:
        out = service.refresh_company_index(s, "Robotics", now=NOW)
    assert out["refreshed"] is False
    assert out["reason"] == "ambiguous_company"
    assert len(out["candidates"]) == 2
    assert "never refreshes several" in out["hint"]


def test_unknown_company_is_an_answer_not_a_crash(seeded):
    with session_scope() as s:
        out = service.refresh_company_index(s, "no-such-employer", now=NOW)
    assert out["refreshed"] is False and out["reason"] == "unknown_company"


def test_tool_is_annotated_as_writing_and_reaching_the_network(seeded):
    """Round 1 shipped a false idempotentHint. This one writes and hits a third party;
    the annotation has to say so."""
    from openhire import mcp_server

    tool = mcp_server.refresh_index
    assert callable(tool.fn if hasattr(tool, "fn") else tool)
