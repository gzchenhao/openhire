"""ghost_score (protocol field ③) — pure-function unit tests.

The formula WILL iterate; these tests pin the current v0 behavior so any change is
deliberate and reviewed.

    ghost_score = min(1.0, 0.15 * relist_count
                          + max(0, days_since - 45) / 90 * 0.5)
"""

import datetime as dt

import pytest

from openhire.pipeline.ghost_score import (
    compute_ghost_score,
    ghost_score_from_parts,
)


def test_fresh_never_relisted_is_zero():
    assert ghost_score_from_parts(relist_count=0, days_since_first_seen=0) == 0.0


def test_within_grace_window_no_staleness_penalty():
    # 45-day grace: anything up to 45 days old with no relists stays at 0.
    assert ghost_score_from_parts(0, 45) == 0.0
    assert ghost_score_from_parts(0, 44.9) == 0.0


def test_staleness_after_grace():
    # 45 + 90 = 135 days → full staleness term = 0.5.
    assert ghost_score_from_parts(0, 135) == pytest.approx(0.5)
    # halfway through the 90-day span → 0.25.
    assert ghost_score_from_parts(0, 90) == pytest.approx(0.25)


def test_relist_term():
    assert ghost_score_from_parts(1, 0) == pytest.approx(0.15)
    assert ghost_score_from_parts(3, 0) == pytest.approx(0.45)


def test_combined_terms():
    # 2 relists (0.30) + 90 days old (0.25) = 0.55
    assert ghost_score_from_parts(2, 90) == pytest.approx(0.55)


def test_clamped_to_one():
    assert ghost_score_from_parts(100, 10000) == 1.0
    assert ghost_score_from_parts(7, 0) == 1.0  # 7 * 0.15 = 1.05 → clamp


def test_monotonic_in_relist_count():
    prev = -1.0
    for r in range(0, 8):
        val = ghost_score_from_parts(r, 30)
        assert val >= prev
        prev = val


def test_monotonic_in_age():
    prev = -1.0
    for d in range(0, 400, 10):
        val = ghost_score_from_parts(1, d)
        assert val >= prev
        prev = val


def test_output_always_in_unit_interval():
    for r in range(0, 20):
        for d in range(0, 500, 25):
            v = ghost_score_from_parts(r, d)
            assert 0.0 <= v <= 1.0


def test_compute_from_datetime_matches_parts():
    now = dt.datetime(2026, 7, 9, tzinfo=dt.timezone.utc)
    first_seen = now - dt.timedelta(days=135)
    assert compute_ghost_score(0, first_seen, now) == pytest.approx(0.5, abs=1e-6)


def test_compute_is_pure_and_clock_injectable():
    # Same inputs → same output, independent of wall clock.
    now = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    fs = now - dt.timedelta(days=200)
    a = compute_ghost_score(1, fs, now)
    b = compute_ghost_score(1, fs, now)
    assert a == b


def test_naive_datetime_is_treated_as_utc():
    now_naive = dt.datetime(2026, 7, 9)
    fs_naive = now_naive - dt.timedelta(days=135)
    # Should not raise on naive/aware mixing and should match the aware result.
    assert compute_ghost_score(0, fs_naive, now_naive) == pytest.approx(0.5, abs=1e-6)
