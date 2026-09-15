"""ghost_score — protocol field ③.

A pure, explainable, unit-tested function. It intentionally has NO dependency on the
database, network, or clock (the caller passes `now`), so it can be reasoned about and
frozen by tests. The formula WILL iterate; the contract is that it stays a pure function
of (relist_count, age_anchor) — never of anything purchasable.

    ghost_score = min(1.0,
        0.15 * relist_count
        + max(0, days_since(age_anchor) - 45) / 90 * 0.5)

`age_anchor` is the EMPLOYER'S OWN posting date (`posted_at`) whenever their ATS reports
one, and only falls back to `first_seen_at` — the day we first saw the row — when it does
not. The parameter used to be called `first_seen_at`, which was true of the first version
and has been wrong since posting dates landed: a reader of this file concluded we score
employers off our own crawl date, which would make every number we publish about them
indefensible. Every caller already passes `posted_at or first_seen_at`; only the name
lied.

Intuition: a posting that is repeatedly relisted, or that has hung around far past a
plausible hiring window, scores higher (worse). Lower is better.
"""

from __future__ import annotations

import datetime as dt

# Tunables — named so the formula reads like the spec and tests can reference them.
RELIST_WEIGHT = 0.15
STALE_GRACE_DAYS = 45
STALE_SPAN_DAYS = 90
STALE_WEIGHT = 0.5


def ghost_score_from_parts(relist_count: int, days_open: float) -> float:
    """Core formula over primitive inputs (easiest to unit-test)."""
    relist_term = RELIST_WEIGHT * max(0, relist_count)
    stale_term = max(0.0, days_open - STALE_GRACE_DAYS) / STALE_SPAN_DAYS * STALE_WEIGHT
    return min(1.0, relist_term + stale_term)


def compute_ghost_score(
    relist_count: int,
    age_anchor: dt.datetime,
    now: dt.datetime | None = None,
) -> float:
    """Compute ghost_score for a job. `age_anchor` is the employer's `posted_at` when
    their ATS reports one, else `first_seen_at`. `now` is injected for determinism."""
    now = now or dt.datetime.now(dt.timezone.utc)
    age_anchor = _as_aware(age_anchor)
    now = _as_aware(now)
    days = (now - age_anchor).total_seconds() / 86400.0
    return ghost_score_from_parts(relist_count, days)


def _as_aware(d: dt.datetime) -> dt.datetime:
    if d.tzinfo is None:
        return d.replace(tzinfo=dt.timezone.utc)
    return d


def ghost_reason(relist_count: int, days_open: float) -> str:
    """Which input drove the score — the thing the number alone will not tell you.

    `verified_at` and `ghost_score` answer different questions, and a caller that reads them
    as one gets a contradiction: a posting can be confirmed live today AND score 1.0. Live
    means the employer's ATS still returns it; the score means it has been returned for a
    very long time, or keeps being relisted. This names which of the two is doing the work,
    so an agent can say "open 368 days, never relisted" instead of "ghost=1.0".
    """
    relist_term = RELIST_WEIGHT * max(0, relist_count)
    stale_term = max(0.0, days_open - STALE_GRACE_DAYS) / STALE_SPAN_DAYS * STALE_WEIGHT
    days = int(days_open)
    if relist_term == 0 and stale_term == 0:
        return f"fresh: {days}d old, never relisted"
    if relist_term == 0:
        return f"age only: open {days}d, never relisted"
    if stale_term == 0:
        return f"relists only: relisted {relist_count}x in {days}d"
    bigger = "age" if stale_term >= relist_term else "relists"
    return f"{bigger} dominant: open {days}d, relisted {relist_count}x"
