"""P0-2 regression: datePosted / days_open / ghost_score use the REAL ATS posting date.

Before the fix, datePosted was our crawl date and ghost_score was stuck at 0 because age
was measured from first_seen_at (≈ crawl time). Now posted_at (the ATS date) anchors both,
falling back to first_seen_at only when the ATS exposes no date.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from openhire import service
from openhire.db import Company, Job, init_db, session_scope
from openhire.pipeline.ghost_score import compute_ghost_score

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 7, 12, tzinfo=UTC)


def _job(jid, posted_at, first_seen, relist=0):
    return Job(
        id=jid, company_id="acme", title="Rust Infra", description_raw="x",
        skills=["rust"], remote_policy="remote", first_seen_at=first_seen,
        verified_at=first_seen, posted_at=posted_at, source="ats_public_api",
        ghost_score=0.0, relist_count=relist,
        apply_channel="https://boards.greenhouse.io/embed/job_app?for=acme&token=1",
        content_hash="h",
    )


@pytest.fixture()
def seeded():
    init_db()
    with session_scope() as s:
        for t in (Job, Company):
            for row in s.execute(select(t)).scalars():
                s.delete(row)
        s.flush()
        s.add(Company(id="acme", name="Acme AI", ats_vendor="greenhouse",
                      ats_tenant="acme", careers_url="x", last_crawled_at=NOW))
        # Posted 100 days before "now"; we only first crawled it 2 days ago.
        s.add(_job("acme:old", NOW - dt.timedelta(days=100), NOW - dt.timedelta(days=2)))
        # No ATS date → must fall back to first_seen_at.
        s.add(_job("acme:nodate", None, NOW - dt.timedelta(days=2)))
    yield


def test_dateposted_is_real_ats_date_not_crawl_date(seeded):
    with session_scope() as s:
        job = s.get(Job, "acme:old")
        payload = service.job_posting(job, s.get(Company, "acme"), ["rust"], NOW)
    assert payload["datePosted"] == (NOW - dt.timedelta(days=100)).date().isoformat()
    assert payload["days_open"] == 100  # real age, not ~2 crawl days


def test_dateposted_falls_back_to_first_seen_when_ats_has_no_date(seeded):
    with session_scope() as s:
        job = s.get(Job, "acme:nodate")
        payload = service.job_posting(job, s.get(Company, "acme"), ["rust"], NOW)
    assert payload["datePosted"] == (NOW - dt.timedelta(days=2)).date().isoformat()
    assert payload["days_open"] == 2


def test_ghost_score_ages_off_real_posting_date():
    # A posting open 100 days is well past the 45-day grace → ghost_score > 0.
    old = compute_ghost_score(0, NOW - dt.timedelta(days=100), NOW)
    fresh = compute_ghost_score(0, NOW - dt.timedelta(days=2), NOW)
    assert old > 0.0
    assert fresh == 0.0
    # 100 days: (100-45)/90 * 0.5 ≈ 0.3055
    assert round(old, 3) == 0.306
