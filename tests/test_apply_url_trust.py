"""apply_channel is the one field where third-party text becomes an action.

Every other string we return is read by a human or an agent. This one gets passed to
`webbrowser.open` by `ohp apply`, and it arrived in an employer's ATS response. Nothing
re-checked it: `resolve_apply_channel` only constrains what we BUILD, not what was already
stored, and not what a vendor might return tomorrow.

Measured 2026-09-20: 18 distinct hosts across 16,261 live rows, all ATS vendors. Nothing
has ever failed this check. It exists so that the first thing that does fails closed.
"""

from __future__ import annotations

import pytest

from openhire.ats import apply_url_is_trusted


@pytest.mark.parametrize("url", [
    "https://boards.greenhouse.io/embed/job_app?for=mongodb&token=8023912",
    "https://job-boards.greenhouse.io/acme/jobs/123",
    "https://jobs.lever.co/acme/abc-def",
    "https://jobs.ashbyhq.com/acme/xyz",
    "https://app.mokahr.com/apply/acme/1234#/job/9",
    "https://unitree.zhiye.com/social/detail?jobAdId=abc",   # per-tenant Beisen host
    "https://www.lixiang.com/employ/detail/275.html",         # first-party employer page
])
def test_real_ats_urls_are_trusted(url):
    assert apply_url_is_trusted(url) is True


@pytest.mark.parametrize("url,why", [
    (None, "missing"),
    ("", "empty"),
    ("http://boards.greenhouse.io/x", "plain http, not https"),
    ("https://example.com/apply", "an employer self-hosted page we cannot vouch for"),
    # The two shapes a lazy check would wave through:
    ("https://evil-zhiye.com/social/detail", "suffix match without the dot"),
    ("https://zhiye.com.attacker.net/social", "the known domain as a prefix of another"),
    ("https://boards.greenhouse.io.evil.net/x", "same trick on an exact host"),
    ("https://attacker.net/?u=jobs.lever.co", "known host only in the query"),
    ("javascript:alert(1)", "not even a web URL"),
])
def test_a_url_we_would_not_open_is_not_trusted(url, why):
    assert apply_url_is_trusted(url) is False, why

