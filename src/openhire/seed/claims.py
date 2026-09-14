"""Verified employer claims — the durable record, kept in the repo on purpose.

A claim cannot live only in the database. The index is rebuilt every Monday by CI
(`ohp seed` → `ohp ingest --all` → `ohp snapshot-build`) starting from the published
snapshot, and a maintainer's local edit would never reach it. Keeping claims here means
they are re-applied on every refresh, they ship inside the public snapshot, and each one is
a reviewable diff with a date and a verification note rather than an opaque row.

This file is DECLARATIVE and authoritative: deleting an entry withdraws that claim.

--- What an employer can and cannot change ---------------------------------------

Cannot: their position in results. Ranking is a locked pure function of (match, freshness).
Cannot: their ghost_score. It is a pure function of (relist_count, posting age) and a test
        freezes the signature. An employer explanation sits BESIDE the score, never on it.

Can: explain. Four corrections, each matching a real situation employers are actually in:

  1. `date_semantics="requisition_created"` — their ATS reports the day the requisition was
     opened internally, not the day it went live. We found employers whose median reads past
     two years, which is not a hiring reality; it is a field meaning something else. This is
     the single most unfair misreading in the index and it is not the employer's fault.
  2. `evergreen_titles` — roles they hire for continuously. There is no single opening to
     fill, so "open 300 days" is the design, not neglect.
  3. `hard_to_fill_titles` — genuinely open, the market is just thin. Common in robotics.
  4. `closed_titles` — no longer hiring, and their ATS has not caught up. The employer is
     authoritative about their own hiring; we surface it so an agent stops sending people.

Titles are matched the way `role_group` is computed (company + case-folded, whitespace-
normalised title), so a declaration survives the employer deleting and re-posting the role
under a new ATS id — which is exactly when they would otherwise have to re-file it.

Verification is by corporate identity (GitHub org membership, or a reply from a corporate
domain), NEVER by payment. Record the method in `note`, without the person's name.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Claim:
    company_id: str          # must match companies.id (our slug)
    claimed_on: dt.date      # the day identity was verified
    note: str                # how it was verified — no names, no addresses

    # The employer's own reply-time commitment. Protocol field ④.
    response_sla_days: int | None = None

    # "publish" (default) | "requisition_created" — what their ATS's date field means.
    date_semantics: str | None = None

    # Exact job titles, as the employer publishes them.
    evergreen_titles: tuple[str, ...] = ()
    hard_to_fill_titles: tuple[str, ...] = ()
    closed_titles: tuple[str, ...] = ()

    # Optional free-text the employer wants shown on a specific title.
    notes_by_title: dict[str, str] = field(default_factory=dict)


# No claims yet. Claims arrive via .github/ISSUE_TEMPLATE/employer_claim.yml
CLAIMS: list[Claim] = []


# --- lookup used at read time (no storage, no migration, always matches this file) ---
_STATUS_FIELDS = (
    ("evergreen", "evergreen_titles"),
    ("hard_to_fill", "hard_to_fill_titles"),
    ("closed", "closed_titles"),
)

_CANNED = {
    "evergreen": "雇主声明：这是常年开放的岗位，随到随收，没有单一空缺。在架时间长是设计如此，不是没人管。",
    "hard_to_fill": "雇主声明：这个岗位仍在招，只是合适的人难找。",
    "closed": "雇主声明：已经不招了，他们的招聘系统还没同步下架。",
}


def _norm(title: str) -> str:
    import re

    return re.sub(r"\s+", " ", (title or "").strip().casefold())


def claim_for(company_id: str) -> Claim | None:
    for c in CLAIMS:
        if c.company_id == company_id:
            return c
    return None


def employer_correction(company_id: str, title: str) -> dict | None:
    """What this employer has said about this specific role, if anything.

    Returns None when the employer has not claimed, or has claimed but said nothing about
    this title — which is the overwhelmingly common case and must stay cheap.
    """
    claim = claim_for(company_id)
    if claim is None:
        return None
    key = _norm(title)
    status = None
    for name, attr in _STATUS_FIELDS:
        if any(_norm(t) == key for t in getattr(claim, attr)):
            status = name
            break
    note = next(
        (v for k, v in claim.notes_by_title.items() if _norm(k) == key),
        None,
    )
    if status is None and note is None and not claim.date_semantics:
        return None
    out: dict = {}
    if status:
        out["status"] = status
    if note or status:
        out["note"] = note or _CANNED.get(status or "", "")
    if claim.date_semantics and claim.date_semantics != "publish":
        out["date_semantics"] = claim.date_semantics
    return out or None
