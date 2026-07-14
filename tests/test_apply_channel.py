"""apply_channel (protocol field ⑤) must always deep-link to the specific job.

"点开就能投" is a product promise. These tests lock the resolver: a vendor URL is only
trusted when it is a canonical ATS-host deep link; employer self-hosted embeds fall back
to a guaranteed-deep-linking canonical ATS apply URL. The job id must appear in every
resolved URL.
"""

from __future__ import annotations

from urllib.parse import urlparse

import pytest

from openhire.ats.base import (
    ATS_APPLY_HOSTS,
    canonical_apply_url,
    resolve_apply_channel,
)

ALL_ATS_HOSTS = {h for hosts in ATS_APPLY_HOSTS.values() for h in hosts}


# --- core invariant: every resolved apply_channel deep-links to the job -------
CASES = [
    # (vendor, tenant, job_id, vendor_url, expect_fallback, expect_embed)
    # Greenhouse — canonical hosted job page is trusted.
    ("greenhouse", "anthropic", "5222180008",
     "https://job-boards.greenhouse.io/anthropic/jobs/5222180008", False, False),
    ("greenhouse", "mongodb", "7310506",
     "https://boards.greenhouse.io/mongodb/jobs/7310506", False, False),
    # Greenhouse — the reported CoreWeave embed bug: id only in query, malformed bare
    # numeric param, opens a listing page → must fall back.
    ("greenhouse", "coreweave", "4681918006",
     "https://coreweave.com/careers/job?4681918006&board=coreweave&gh_jid=4681918006",
     True, True),
    ("greenhouse", "databricks", "8437000002",
     "https://databricks.com/company/careers/open-positions/job?gh_jid=8437000002",
     True, True),
    ("greenhouse", "samsara", "7617960",
     "https://www.samsara.com/company/careers/roles/7617960?gh_jid=7617960", True, True),
    # Missing vendor URL → fall back, but not classified as an embed.
    ("greenhouse", "figma", "999", None, True, False),
    # Lever — apply form on ATS host is trusted.
    ("lever", "mistral", "abc-123",
     "https://jobs.lever.co/mistral/abc-123/apply", False, False),
    ("lever", "palantir", "xyz-9",
     "https://jobs.lever.co/palantir/xyz-9", False, False),
    # Ashby — application URL on ATS host is trusted.
    ("ashby", "openai", "8fb1615c",
     "https://jobs.ashbyhq.com/openai/8fb1615c/application", False, False),
]


@pytest.mark.parametrize("vendor,tenant,jid,vurl,exp_fallback,exp_embed", CASES)
def test_resolution(vendor, tenant, jid, vurl, exp_fallback, exp_embed):
    res = resolve_apply_channel(vendor, tenant, jid, vurl)
    # THE promise: the resolved URL always contains the specific job id.
    assert jid in res.url, f"{res.url} does not deep-link to job {jid}"
    # And it is always on a deep-linkable ATS host (never an employer embed domain).
    host = urlparse(res.url).netloc.lower()
    assert host in ALL_ATS_HOSTS, f"{host} is not a canonical ATS host"
    assert res.url.startswith("https://")
    assert res.used_fallback is exp_fallback
    assert res.is_embed is exp_embed


def test_coreweave_bug_exact_fix():
    """The exact reported URL becomes the clean Greenhouse application form."""
    bad = "https://coreweave.com/careers/job?4681918006&board=coreweave&gh_jid=4681918006"
    res = resolve_apply_channel("greenhouse", "coreweave", "4681918006", bad)
    assert res.url == (
        "https://boards.greenhouse.io/embed/job_app?for=coreweave&token=4681918006"
    )
    # The stray bare numeric param is gone.
    assert "?4681918006&" not in res.url


def test_canonical_urls_contain_job_id_and_are_https():
    for vendor in ("greenhouse", "lever", "ashby"):
        url = canonical_apply_url(vendor, "acme", "JOB42")
        assert "JOB42" in url
        assert url.startswith("https://")
        assert urlparse(url).netloc.lower() in ALL_ATS_HOSTS


def test_resolution_is_idempotent():
    """Re-resolving an already-canonical URL must not change it (safe to re-run)."""
    first = resolve_apply_channel(
        "greenhouse", "coreweave", "4681918006",
        "https://coreweave.com/careers/job?gh_jid=4681918006",
    ).url
    second = resolve_apply_channel("greenhouse", "coreweave", "4681918006", first).url
    assert first == second


def test_embed_never_leaks_employer_domain():
    """An employer-domain embed URL must never survive as the apply_channel."""
    res = resolve_apply_channel(
        "greenhouse", "brex", "12345", "https://www.brex.com/careers/12345?gh_jid=12345"
    )
    assert "brex.com" not in res.url
    assert urlparse(res.url).netloc.lower() in ALL_ATS_HOSTS
