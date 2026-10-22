"""DeepSeek runs only at half price (pipeline/pricing.py), and nothing can switch that off.

On 2026-10-22 a session ran the paid role-family pass on a weekday afternoon in Beijing
and paid ¥12.50 for about ¥6 of work, although the rule to run off-peak had been written
down since 2026-09-23. The rule is now code. What is locked down here:
  * the bands: weekdays 09:00-12:00 and 14:00-18:00 Beijing are refused, padded by 30
    minutes on each side; weekends and every other hour are allowed;
  * every DeepSeek call refuses before sending anything, `extract` falls back to the free
    heuristic and stamps it heuristic, and GLM (a prepaid plan) is untouched;
  * both paid passes do nothing at full price, stop at the batch boundary when a run
    crosses into it, and leave the unfinished rows for the next run;
  * the CLI says when to come back and exits non-zero; no environment variable exists to
    turn the lock off.
"""

from __future__ import annotations

import datetime as dt
import inspect
from pathlib import Path

import pytest
from sqlalchemy import select
from typer.testing import CliRunner

from openhire import config
from openhire.cli import app
from openhire.db import Job, init_db, session_scope
from openhire.db.models import Company
from openhire.pipeline import pricing, rebuild
from openhire.pipeline.extract import (
    DeepSeekExtractor,
    ExtractionResult,
    GLMExtractor,
)
from openhire.pipeline.pricing import PeakHours
from openhire.ats.base import JobRecord

BJ = pricing.BEIJING
UTC = dt.timezone.utc

# Thursday 2026-10-22 (the day of the expensive run) and the weekend after it.
THU = dt.date(2026, 10, 22)
SAT = dt.date(2026, 10, 24)
SUN = dt.date(2026, 10, 25)
MON = dt.date(2026, 10, 26)


def _bj(day: dt.date, hh: int, mm: int = 0) -> dt.datetime:
    return dt.datetime(day.year, day.month, day.day, hh, mm, tzinfo=BJ)


def _at(monkeypatch, when: dt.datetime) -> None:
    monkeypatch.setattr(pricing, "_now", lambda: when)


# --- the bands ------------------------------------------------------------------
@pytest.mark.parametrize(
    "when, until",
    [
        (_bj(THU, 8, 29), None),
        (_bj(THU, 8, 30), (12, 30)),     # 30 minutes before full price starts
        (_bj(THU, 9, 0), (12, 30)),
        (_bj(THU, 12, 29), (12, 30)),
        (_bj(THU, 12, 30), None),        # the lunch hour is half price
        (_bj(THU, 13, 29), None),
        (_bj(THU, 13, 30), (18, 30)),
        (_bj(THU, 15, 8), (18, 30)),     # when the 2026-10-22 run happened
        (_bj(THU, 18, 29), (18, 30)),
        (_bj(THU, 18, 30), None),
        (_bj(THU, 21, 30), None),        # the local session's nightly run
        (_bj(THU, 3, 0), None),
        (_bj(SAT, 10, 0), None),         # weekends are half price all day
        (_bj(SUN, 15, 0), None),
        (_bj(MON, 8, 30), (12, 30)),
    ],
)
def test_bands(when, until):
    got = pricing.blocked_until(when)
    if until is None:
        assert got is None
    else:
        assert got is not None and (got.hour, got.minute) == until
        assert got.date() == when.date() and got.utcoffset() == dt.timedelta(hours=8)


def test_any_timezone_is_read_as_beijing_time():
    # 07:08 UTC on Thursday is 15:08 in Beijing, and 14:08 on the lead's PC (UTC+7).
    utc = dt.datetime(2026, 10, 22, 7, 8, tzinfo=UTC)
    local = utc.astimezone(dt.timezone(dt.timedelta(hours=7)))
    assert pricing.blocked_until(utc) == pricing.blocked_until(local) == _bj(THU, 18, 30)
    # 23:00 UTC on Friday is already Saturday morning in Beijing.
    assert pricing.blocked_until(dt.datetime(2026, 10, 23, 23, 0, tzinfo=UTC)) is None


def test_explain_says_when_to_come_back():
    msg = pricing.explain(_bj(THU, 15, 8))
    assert "15:08" in msg and "18:30" in msg and "半价" in msg
    assert pricing.explain(_bj(SAT, 15, 8)) is None
    with pytest.raises(PeakHours):
        pricing.check(_bj(THU, 15, 8))
    pricing.check(_bj(THU, 21, 30))  # no raise


def test_no_switch_turns_the_lock_off():
    src = Path(pricing.__file__).read_text(encoding="utf-8")
    assert "import os" not in src and "os.environ" not in src and "getenv" not in src
    call = inspect.getsource(DeepSeekExtractor._call)
    assert call.index("pricing.check()") < call.index(".post(")


# --- the extractor ----------------------------------------------------------------
class _Resp:
    status_code = 200

    def __init__(self, content: str):
        self._content = content

    def json(self):
        return {
            "choices": [{"message": {"content": self._content}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 10},
        }

    def raise_for_status(self):
        pass


class _Client:
    def __init__(self, content: str):
        self.posts = 0
        self._content = content

    def post(self, url, json=None):
        self.posts += 1
        return _Resp(self._content)


def _record() -> JobRecord:
    return JobRecord(
        ats_job_id="1", title="Perception Engineer",
        description_raw="We need C++ and CUDA for perception.", apply_channel="https://x",
    )


def _deepseek(content='{"skills": ["c++", "cuda"], "remote_policy": "onsite"}'):
    ext = DeepSeekExtractor("k", "https://example.invalid", "m")
    ext._client = _Client(content)
    return ext


def test_deepseek_call_refuses_at_full_price_without_sending(monkeypatch):
    _at(monkeypatch, _bj(THU, 15, 8))
    ext = _deepseek()
    with pytest.raises(PeakHours):
        ext.extract_with_usage(_record())
    with pytest.raises(PeakHours):
        ext.classify_role_family_with_usage(_record())
    assert ext._client.posts == 0


def test_deepseek_call_goes_out_at_half_price(monkeypatch):
    _at(monkeypatch, _bj(THU, 21, 30))
    ext = _deepseek()
    result, pin, _ = ext.extract_with_usage(_record())
    assert ext._client.posts == 1 and pin == 100 and result.extractor == "deepseek"


def test_extract_falls_back_to_the_heuristic_and_says_so(monkeypatch):
    _at(monkeypatch, _bj(THU, 15, 8))
    ext = _deepseek()
    result = ext.extract(_record())
    assert ext._client.posts == 0
    assert result.extractor == "heuristic"  # so the monthly paid pass still picks it up


def test_glm_is_not_locked(monkeypatch):
    _at(monkeypatch, _bj(THU, 15, 8))
    ext = GLMExtractor(["key-1"], "https://example.invalid/api/coding/paas/v4", "glm-5.3-flash")
    client = _Client('{"role_family": "engineering"}')
    monkeypatch.setattr(GLMExtractor, "_http", lambda self: client)
    label, _, _ = ext.classify_role_family_with_usage(_record())
    assert label == "engineering" and client.posts == 1


# --- the paid passes ----------------------------------------------------------------
class _FakeDeepSeek:
    def __init__(self):
        self.calls = 0

    def extract_with_usage(self, rec):
        self.calls += 1
        return ExtractionResult(skills=["go"], remote_policy="onsite", salary_min=None,
                                salary_max=None, salary_currency=None), 1000, 50

    def classify_role_family_with_usage(self, rec):
        self.calls += 1
        return "engineering", 500, 5


@pytest.fixture()
def ten_jobs():
    init_db()
    now = dt.datetime.now(UTC)
    with session_scope() as s:
        for t in (Job, Company):
            for row in s.execute(select(t)).scalars():
                s.delete(row)
        s.flush()
        s.add(Company(id="acme", name="Acme", ats_vendor="greenhouse", ats_tenant="acme",
                      careers_url="x", last_crawled_at=now))
        for i in range(10):
            s.add(Job(
                id=f"acme:{i}", company_id="acme", title=f"Role {i}",
                description_raw="rust k8s", skills=["rust"], remote_policy="remote",
                first_seen_at=now, verified_at=now, source="ats_public_api",
                apply_channel="https://x", content_hash=f"h{i}", ghost_score=0.0,
                extraction_source="heuristic", role_family=None,
            ))
    return now


def _sources_and_families():
    with session_scope() as s:
        rows = s.execute(select(Job.extraction_source, Job.role_family)).all()
    return [r[0] for r in rows], [r[1] for r in rows]


def test_both_passes_do_nothing_at_full_price(ten_jobs, monkeypatch):
    _at(monkeypatch, _bj(THU, 15, 8))
    fake = _FakeDeepSeek()
    monkeypatch.setattr(rebuild, "make_deepseek_extractor", lambda: fake)

    for run in (rebuild.rebuild_extraction, rebuild.rebuild_role_family):
        stats = run(batch_size=5, workers=2, ceiling_cny=999)
        assert stats.peak_blocked and stats.halted
        assert stats.total_target == 10 and stats.processed == 0 and stats.cost == 0
        assert "18:30" in stats.halt_reason
    assert fake.calls == 0
    sources, families = _sources_and_families()
    assert set(sources) == {"heuristic"} and set(families) == {None}


def test_a_run_that_crosses_into_full_price_stops_at_the_batch_boundary(ten_jobs, monkeypatch):
    clock = iter([_bj(THU, 13, 29)] + [_bj(THU, 13, 30)] * 50)
    monkeypatch.setattr(pricing, "_now", lambda: next(clock))
    fake = _FakeDeepSeek()
    monkeypatch.setattr(rebuild, "make_deepseek_extractor", lambda: fake)

    stats = rebuild.rebuild_role_family(batch_size=4, workers=2, ceiling_cny=999)
    assert stats.peak_blocked and stats.processed == 4 and stats.updated == 4
    assert fake.calls == 4
    _, families = _sources_and_families()
    assert families.count("engineering") == 4 and families.count(None) == 6  # next run's


def test_a_glm_run_is_not_stopped(ten_jobs, monkeypatch):
    _at(monkeypatch, _bj(THU, 15, 8))

    class _FakeGLM(_FakeDeepSeek):
        name = "glm"

    monkeypatch.setattr(rebuild, "make_llm_extractor", lambda backend, model: _FakeGLM())
    stats = rebuild.rebuild_role_family(batch_size=5, workers=2, ceiling_cny=999, backend="glm")
    assert not stats.peak_blocked and stats.updated == 10


def test_a_call_refused_mid_batch_is_not_retried(monkeypatch):
    calls = []

    def refused():
        calls.append(1)
        raise PeakHours("full price")

    value, err, limited = rebuild._retry_call(refused)
    assert value is None and err.startswith("PeakHours") and not limited
    assert len(calls) == 1


# --- the CLI ----------------------------------------------------------------------
runner = CliRunner()


def test_cli_paid_passes_say_when_to_come_back_and_exit_non_zero(ten_jobs, monkeypatch):
    _at(monkeypatch, _bj(THU, 15, 8))
    fake = _FakeDeepSeek()
    monkeypatch.setattr(rebuild, "make_deepseek_extractor", lambda: fake)
    for cmd in (["extract-role-family", "--ceiling", "2"], ["extract-rebuild", "--ceiling", "15"]):
        res = runner.invoke(app, cmd, env={"COLUMNS": "200"})
        assert res.exit_code == 1, res.output
        assert "ERR_DEEPSEEK_FULL_PRICE" in res.output and "18:30" in res.output
        assert "完成" not in res.output
    assert fake.calls == 0


def test_cli_sample_and_bootstrap_refuse_before_starting(monkeypatch):
    _at(monkeypatch, _bj(THU, 15, 8))
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setattr(config, "EXTRACTOR", config.EXTRACTOR)  # bootstrap sets it

    def must_not_run(*a, **k):
        raise AssertionError("a paid run started at full price")

    monkeypatch.setattr(rebuild, "make_deepseek_extractor", must_not_run)
    res = runner.invoke(app, ["extract-sample", "--n", "5"], env={"COLUMNS": "200"})
    assert res.exit_code == 1 and "ERR_DEEPSEEK_FULL_PRICE" in res.output

    res = runner.invoke(app, ["bootstrap", "--deepseek", "--force", "--yes"],
                        env={"COLUMNS": "200"})
    assert res.exit_code == 1 and "ERR_DEEPSEEK_FULL_PRICE" in res.output
    assert "--deepseek" in res.output  # and how to go ahead for free right now
