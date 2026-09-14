"""Verified employer claims — the durable record, kept in the repo on purpose.

A claim cannot live only in the database. The index is rebuilt every Monday by CI
(`ohp seed` → `ohp ingest --all` → `ohp snapshot-build`) starting from the published
snapshot, and a maintainer's local edit would never reach it. Keeping claims here means
`ohp seed` re-applies them on every refresh, they ship inside the public snapshot, and each
one is a reviewable diff with a date and a verification note rather than an opaque row.

This file is DECLARATIVE and authoritative: `apply_claims` makes the database match it, so
deleting an entry withdraws that claim on the next run. Nothing here touches ranking —
ranking is a locked pure function of (match, freshness), and no claim can buy a position.

Verification is by corporate identity (GitHub org membership, or a reply from a
corporate-domain address), NEVER by payment. Record how it was verified in `note`, without
the person's name or address — the proof is checked, not published.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass


@dataclass(frozen=True)
class Claim:
    company_id: str          # must match companies.id (our slug)
    claimed_on: dt.date      # the day identity was verified
    note: str                # how it was verified — no names, no addresses
    response_sla_days: int | None = None  # only if the employer committed to one


# No claims yet. The template that produces them:
# .github/ISSUE_TEMPLATE/employer_claim.yml
CLAIMS: list[Claim] = []
