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

# Freshness decays over this horizon, measured on the EMPLOYER's clock: days since the
# ATS last touched the posting, or since it was posted when the ATS reports no touch.
# It used to be days since verified_at, which is the index build time and therefore the
# same number on every row: three testers found a 484-day posting ranked above a 14-day
# one at equal match because the freshness term never varied. 180 days: a 2-week posting
# scores ~0.92, the median 62-day posting ~0.66, anything past six months 0.
FRESHNESS_HORIZON_DAYS = 180.0


def rank_score(match_quality: float, freshness: float) -> float:
    """The one and only ranking function. Pure. Two inputs. Never money-driven."""
    m = _clamp01(match_quality)
    f = _clamp01(freshness)
    return MATCH_WEIGHT * m + FRESHNESS_WEIGHT * f


import re

# Same fold the service filter uses: the extractor emits "computer vision" and
# "computer-vision" for one skill, so a score computed on raw strings disagrees with the
# filter that selected the row. Both sides must use this.
_SKILL_SEP_RE = re.compile(r"[-_\s]+")


def normalize_skill(tag: str) -> str:
    return _SKILL_SEP_RE.sub(" ", (tag or "").strip().lower())


# One concept, many spellings. The extractor stores whatever the JD said, so "占用网络",
# "occ", "occupancy" and "occupancy networks" are four tags for one thing, and a Chinese
# engineer typing 感知 found nothing while the index held 感知 jobs tagged in English.
# Expansion is query-side only: a requested skill matches a row if ANY alias is on it.
# Keys and values are in normalize_skill() form (lower, separators folded to one space).
_SKILL_ALIASES: dict[str, tuple[str, ...]] = {
    "感知": ("perception", "3d perception", "三维感知", "感知算法"),
    "perception": ("感知", "3d perception", "三维感知", "感知算法"),
    "占用网络": ("occ", "occupancy", "occupancy network", "occupancy networks"),
    "occupancy": ("occ", "占用网络", "occupancy network", "occupancy networks"),
    "occ": ("occupancy", "占用网络", "occupancy network", "occupancy networks"),
    "occupancy networks": ("occ", "occupancy", "占用网络", "occupancy network"),
    "occupancy network": ("occ", "occupancy", "占用网络", "occupancy networks"),
    "点云": ("point cloud", "point cloud processing", "point clouds"),
    "point cloud": ("点云", "point cloud processing", "point clouds"),
    "多传感器融合": ("sensor fusion", "multi sensor fusion", "传感器融合"),
    "传感器融合": ("sensor fusion", "multi sensor fusion", "多传感器融合"),
    "sensor fusion": ("多传感器融合", "multi sensor fusion", "传感器融合"),
    "multi sensor fusion": ("多传感器融合", "sensor fusion", "传感器融合"),
    "视觉": ("computer vision", "vision", "视觉算法", "cv"),
    "computer vision": ("视觉", "vision", "视觉算法", "cv"),
    "3d目标检测": ("3d object detection", "object detection", "3d detection", "目标检测"),
    "目标检测": ("object detection", "3d object detection", "3d目标检测"),
    "object detection": ("目标检测", "3d object detection", "3d目标检测"),
    "目标跟踪": ("tracking", "multi object tracking", "object tracking"),
    "tracking": ("目标跟踪", "multi object tracking", "object tracking"),
    "定位": ("localization", "slam", "定位算法"),
    "localization": ("定位", "slam", "定位算法"),
    "规控": ("planning", "planning and control", "motion planning", "规划控制"),
    "规划控制": ("planning", "planning and control", "motion planning", "规控"),
    "planning": ("规控", "motion planning", "规划控制", "planning and control"),
    "bev": ("bev perception", "bev感知"),
    "端到端": ("end to end", "end to end driving", "e2e"),
    "end to end": ("端到端", "end to end driving", "e2e"),
}


def expand_skill(tag: str) -> set[str]:
    """The folded tag plus every alias we know for it. Always contains the tag itself."""
    n = normalize_skill(tag)
    return {n, *(normalize_skill(a) for a in _SKILL_ALIASES.get(n, ()))}


def match_quality(requested_skills: list[str], job_skills: list[str]) -> float:
    """Fraction of requested skills the job matches (intersection / requested).

    With no requested skills, match is neutral (1.0) so ranking falls back to freshness.
    """
    if not requested_skills:
        return 1.0
    # Dedupe on the folded form so "BEV" and "bev" are one request, not two.
    req = {normalize_skill(s): expand_skill(s) for s in requested_skills}
    have = {normalize_skill(s) for s in job_skills}
    return sum(1 for aliases in req.values() if aliases & have) / len(req)


def freshness(anchor: dt.datetime, now: dt.datetime | None = None) -> float:
    """Linear freshness in [0,1] from days since `anchor`: the employer's last-touched
    timestamp, or the posting date when the ATS reports none (see service._freshness_anchor)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    anchor = _aware(anchor)
    now = _aware(now)
    days = (now - anchor).total_seconds() / 86400.0
    return _clamp01(1.0 - days / FRESHNESS_HORIZON_DAYS)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _aware(d: dt.datetime) -> dt.datetime:
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
