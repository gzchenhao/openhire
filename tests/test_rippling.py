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


XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<workzag-jobs>
  <position><id>1234</id><office>Dresden</office><additionalOffices><office>Berlin</office></additionalOffices>
    <name>Robotics Software Engineer (m/w/d)</name><createdAt>2026-10-01T09:30:00+00:00</createdAt>
    <jobDescriptions><jobDescription><name>Your mission</name><value><![CDATA[<p>Build ROS 2 stacks</p>]]></value></jobDescription></jobDescriptions>
  </position>
  <position><id></id><name>broken</name></position>
</workzag-jobs>"""


def test_personio_feed_parses_dates_offices_and_descriptions():
    import xml.etree.ElementTree as ET
    assert detect_board("https://wandelbots.jobs.personio.de/") == ("personio", "wandelbots")
    c = get_client("personio")
    root = ET.fromstring(XML)
    assert c._has_jobs_array(root)
    rows = c.parse(root, "wandelbots")
    assert len(rows) == 1 and rows[0].location == "Dresden; Berlin"
    assert rows[0].posted_at.isoformat().startswith("2026-10-01") and "ROS 2" in rows[0].description_raw
    assert rows[0].apply_channel == "https://wandelbots.jobs.personio.de/job/1234"
