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


# --- ghost_reason (N4 from the round-2 tester report) -------------------------
# The complaint: a posting can read `verified_at = today` and `ghost_score = 1.0` at the
# same time, and the payload offered nothing to reconcile them. The two fields answer
# different questions — "does the ATS still return it?" versus "how long has it been
# returning it?" — and only one of them was ever explained.

def test_ghost_reason_names_age_when_age_is_the_whole_story():
    from openhire.pipeline.ghost_score import ghost_reason, ghost_score_from_parts

    assert ghost_score_from_parts(0, 367) == 1.0
    reason = ghost_reason(0, 367)
    assert "age only" in reason and "367d" in reason and "never relisted" in reason


def test_ghost_reason_names_relists_when_the_posting_is_young():
    from openhire.pipeline.ghost_score import ghost_reason

    assert "relists only" in ghost_reason(3, 10)


def test_ghost_reason_says_fresh_when_the_score_is_zero():
    from openhire.pipeline.ghost_score import ghost_reason, ghost_score_from_parts

    assert ghost_score_from_parts(0, 14) == 0.0
    assert "fresh" in ghost_reason(0, 14)


def test_ghost_reason_tracks_the_same_anchor_the_pipeline_scores_on():
    """The pipeline ages ghost_score off posted_at when the ATS supplies one, falling back
    to first_seen_at. A reason computed off a different anchor would narrate "open 48d"
    beside a stored 1.0 — a confident wrong explanation, worse than none."""
    import datetime as dt
    import inspect

    from openhire import service

    src = inspect.getsource(service.job_posting)
    assert "job.posted_at or job.first_seen_at" in src

    now = dt.datetime(2026, 9, 14, tzinfo=dt.timezone.utc)
    posted = now - dt.timedelta(days=367)
    from openhire.pipeline.ghost_score import compute_ghost_score, ghost_reason

    assert compute_ghost_score(0, posted, now) == 1.0
    assert "367d" in ghost_reason(0, (now - posted).total_seconds() / 86400.0)
