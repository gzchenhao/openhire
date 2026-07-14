"""Result ranking for search_jobs — protocol red line #2.

RED LINE #2 (README §三条隐私红线): "排序不可购买 — 排序函数是 f(匹配度, 新鲜度) 的纯函数，
无任何付费参数". `rank_score` therefore takes EXACTLY two inputs — match_quality and
freshness — and nothing else. Ranking can never be bought: there is no money-driven
input, and the signature is frozen by tests/test_ranking.py.

The server only ever does a HARD FILTER plus this FIXED ranking; precise re-ranking is
deliberately left to the client agent (which has the résumé/context the server never sees).
"""

from __future__ import annotations

import datetime as dt

# Fixed weights — tunable, but the *inputs* are locked to (match_quality, freshness).
MATCH_WEIGHT = 0.7
FRESHNESS_WEIGHT = 0.3

# Freshness decays over this horizon (days since verified_at). A job re-verified today
# scores ~1.0; one last confirmed live 30 days ago scores ~0.
FRESHNESS_HORIZON_DAYS = 30.0


def rank_score(match_quality: float, freshness: float) -> float:
    """The one and only ranking function. Pure. Two inputs. Never money-driven."""
    m = _clamp01(match_quality)
    f = _clamp01(freshness)
    return MATCH_WEIGHT * m + FRESHNESS_WEIGHT * f


def match_quality(requested_skills: list[str], job_skills: list[str]) -> float:
    """Fraction of requested skills the job matches (intersection / requested).

    With no requested skills, match is neutral (1.0) so ranking falls back to freshness.
    """
    if not requested_skills:
        return 1.0
    req = {s.lower() for s in requested_skills}
    have = {s.lower() for s in job_skills}
    return len(req & have) / len(req)


def freshness(verified_at: dt.datetime, now: dt.datetime | None = None) -> float:
    """Linear freshness in [0,1] from days since verified_at (protocol field ①)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    verified_at = _aware(verified_at)
    now = _aware(now)
    days = (now - verified_at).total_seconds() / 86400.0
    return _clamp01(1.0 - days / FRESHNESS_HORIZON_DAYS)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _aware(d: dt.datetime) -> dt.datetime:
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
