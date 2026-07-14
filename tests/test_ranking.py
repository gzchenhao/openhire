"""Red line #2 — ranking is never a paid parameter.

The ranking function's signature is LOCKED to exactly (match_quality, freshness). Any
attempt to add a paid/sponsored/boost input breaks these tests.
"""

from __future__ import annotations

import datetime as dt
import inspect

import pytest

from openhire.pipeline import ranking
from openhire.pipeline.ranking import freshness, match_quality, rank_score

UTC = dt.timezone.utc


def test_rank_score_signature_is_locked():
    params = list(inspect.signature(rank_score).parameters)
    assert params == ["match_quality", "freshness"], (
        f"rank_score signature changed to {params} — ranking must remain a pure "
        "function of (match_quality, freshness) only. No paid parameter allowed."
    )


def test_no_paid_parameter_names_anywhere():
    forbidden = {"sponsored", "paid", "boost", "bid", "price", "promoted", "rank_fee", "budget"}
    for name in ("rank_score", "match_quality", "freshness"):
        fn = getattr(ranking, name)
        for p in inspect.signature(fn).parameters:
            assert p.lower() not in forbidden, f"{name} has a forbidden param '{p}'"


def test_rank_source_has_no_paid_tokens():
    src = inspect.getsource(ranking).lower()
    for tok in ("sponsored", "boost(", "bid", "paid_", "promoted"):
        assert tok not in src, f"ranking module references paid-ranking token '{tok}'"


def test_rank_monotonic_in_match():
    prev = -1.0
    for m in [0.0, 0.25, 0.5, 0.75, 1.0]:
        v = rank_score(m, 0.5)
        assert v >= prev
        prev = v


def test_rank_monotonic_in_freshness():
    prev = -1.0
    for f in [0.0, 0.25, 0.5, 0.75, 1.0]:
        v = rank_score(0.5, f)
        assert v >= prev
        prev = v


def test_rank_output_in_unit_interval():
    for m in [0, 0.3, 1, 2, -1]:
        for f in [0, 0.3, 1, 2, -1]:
            assert 0.0 <= rank_score(m, f) <= 1.0


def test_match_quality():
    assert match_quality(["rust", "k8s"], ["rust", "go"]) == pytest.approx(0.5)
    assert match_quality(["rust"], ["rust", "k8s"]) == pytest.approx(1.0)
    assert match_quality([], ["anything"]) == 1.0  # neutral when nothing requested
    assert match_quality(["cobol"], ["rust"]) == 0.0


def test_match_quality_is_case_insensitive():
    assert match_quality(["Rust", "K8S"], ["rust", "k8s"]) == pytest.approx(1.0)


def test_freshness_recent_is_high_old_is_low():
    now = dt.datetime(2026, 7, 9, tzinfo=UTC)
    assert freshness(now, now) == pytest.approx(1.0)
    assert freshness(now - dt.timedelta(days=15), now) == pytest.approx(0.5)
    assert freshness(now - dt.timedelta(days=60), now) == 0.0
