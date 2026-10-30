"""Rippling board reader (0.8.41, reports/121), ported from career-ops' provider (MIT)."""

from __future__ import annotations

from openhire.ats import get_client
from openhire.ats.boards import detect_board

PAYLOAD = {"items": [
    {"id": "abc-1", "name": "Robotics Software Engineer", "url": "https://ats.rippling.com/mytra/jobs/abc-1",
     "department": {"name": "Engineering"}, "locations": [{"name": "Brisbane, CA"}, {"name": "Brisbane, CA"}]},
    {"id": "abc-2", "name": "Field Technician (Remote)", "url": "https://evil.example.com/x",
     "locations": [{"name": "Remote (US)"}]},
    {"id": "", "name": "no id"},
    {"id": "abc-3", "name": "  "},
], "totalItems": 4}


def test_detects_board_urls():
    assert detect_board("https://ats.rippling.com/mytra/jobs") == ("rippling", "mytra")
    assert detect_board("ats.rippling.com/api/v2/board/bonsai-robotics/jobs?page=0") == ("rippling", "bonsai-robotics")


def test_parse_keeps_id_title_cities_and_only_trusted_apply_links():
    c = get_client("rippling")
    assert c._has_jobs_array(PAYLOAD) and not c._has_jobs_array({"jobs": []})
    rows = c.parse(PAYLOAD, "mytra")
    assert [r.ats_job_id for r in rows] == ["abc-1", "abc-2"]
    assert rows[0].location == "Brisbane, CA" and rows[0].posted_at is None
    assert rows[0].apply_channel == "https://ats.rippling.com/mytra/jobs/abc-1"
    assert rows[1].apply_channel.startswith("https://ats.rippling.com/") and rows[1].remote_hint == "remote"
    assert c.endpoint("mytra") == "https://ats.rippling.com/api/v2/board/mytra/jobs?page=0&pageSize=1000"
