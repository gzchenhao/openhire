"""Comeet careers-API reader (0.8.42, reports/122), ported from career-ops' provider (MIT).
The payload shape is the one Imagry's board returned on 2026-10-30."""

from __future__ import annotations

from openhire.ats import get_client
from openhire.ats.base import apply_url_is_trusted

TENANT = "imagry/B7.00F/7BF2E7A1EFC1EFCF7E7BF36393DF826BB2E7A"

PAYLOAD = [
    {"name": "CO-143 Algo and Control Engineer", "uid": "DD.C68", "department": "R&D",
     "location": {"name": "San Jose, CA", "country": "US", "is_remote": False},
     "time_updated": "2026-06-18T19:39:34Z",
     "url_active_page": "https://imagry.co/jobs-at-imagry/co/san-jose-ca/DD.C68/co-143/all/",
     "url_comeet_hosted_page": "https://www.comeet.com/jobs/imagry/B7.00F/co-143-algo-and-control-engineer/DD.C68",
     "details": [{"name": "Description", "value": "<p>Plan and control for autonomous buses</p>"},
                 {"name": "Requirements", "value": "<ul><li>5+ years of experience</li></ul>"}]},
    {"name": "Field Engineer", "uid": "AA.001", "location": {"name": "Haifa, Israel", "is_remote": True},
     "url_comeet_hosted_page": "https://evil.example.com/AA.001"},
    {"name": "", "uid": "BB.002"},
    "not a position",
]


def test_endpoint_and_board_keep_the_token_out_of_the_board_link():
    c = get_client("comeet")
    assert c.endpoint(TENANT) == ("https://www.comeet.co/careers-api/2.0/company/B7.00F/positions"
                                  "?token=7BF2E7A1EFC1EFCF7E7BF36393DF826BB2E7A&details=true")
    assert c.careers_url(TENANT) == "https://www.comeet.com/jobs/imagry/B7.00F"


def test_parse_reads_details_and_stores_time_updated_as_an_update_not_a_posting_date():
    c = get_client("comeet")
    assert c._has_jobs_array(PAYLOAD) and not c._has_jobs_array({"items": []})
    rows = c.parse(PAYLOAD, TENANT)
    assert [r.ats_job_id for r in rows] == ["DD.C68", "AA.001"]
    first = rows[0]
    assert first.posted_at is None and first.updated_at.isoformat().startswith("2026-06-18")
    assert "autonomous buses" in first.description_raw and "5+ years" in first.description_raw
    assert first.apply_channel == PAYLOAD[0]["url_comeet_hosted_page"]
    assert first.location == "San Jose, CA" and first.remote_hint == "unknown"
    second = rows[1]
    assert second.location == "Haifa, Israel, Remote" and second.remote_hint == "remote"
    # A link off Comeet's host is never stored; the fallback is the employer's board, not a guess.
    assert second.apply_channel == "https://www.comeet.com/jobs/imagry/B7.00F"
    assert "7BF2E7" not in second.apply_channel
    assert all(apply_url_is_trusted(r.apply_channel, "comeet") for r in rows)
