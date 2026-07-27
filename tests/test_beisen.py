"""Beisen (北森 / `<tenant>.zhiye.com`) adapter — hermetic, no network.

The fixture is a real, trimmed `GetJobAdPageList` response captured from
`unitree.zhiye.com` on 2026-07-27 (see reports/014).

The load-bearing assertions here are the two that a Chinese ATS makes easy to get wrong:
  * a year-1 / zero-epoch date must become NULL, never the crawl time (the P0-2 lesson);
  * a monthly CNY salary is stored as published and never annualised.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib

import httpx
import pytest

from openhire.ats import get_client
from openhire.ats.base import canonical_apply_url, resolve_apply_channel
from openhire.ats.beisen import BeisenClient

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "beisen_unitree_page.json"
PAYLOAD = json.loads(FIXTURE.read_text(encoding="utf-8"))
TENANT = "unitree"


@pytest.fixture()
def records():
    return BeisenClient().parse(PAYLOAD, TENANT)


def test_registered_as_a_vendor():
    assert isinstance(get_client("beisen"), BeisenClient)
    assert get_client("beisen").vendor == "beisen"


def test_parses_every_row(records):
    assert len(records) == len(PAYLOAD["Data"])
    assert [r.title for r in records] == [r["JobAdName"] for r in PAYLOAD["Data"]]


def test_five_protocol_fields_present(records):
    for r in records:
        assert r.ats_job_id and r.title
        assert r.description_raw          # 职责 + 任职要求
        assert r.apply_channel.startswith("https://")
        assert r.location


def test_apply_channel_deep_links_to_the_job(records):
    for r, raw in zip(records, PAYLOAD["Data"]):
        # The GUID, not the numeric JobAdId, is what the portal routes on.
        assert r.ats_job_id == raw["Id"]
        assert r.apply_channel == (
            f"https://{TENANT}.zhiye.com/social/detail?jobAdId={raw['Id']}"
        )
        assert raw["Id"] in r.apply_channel
        assert str(raw["JobAdId"]) not in r.apply_channel


def test_apply_channel_is_on_the_employers_own_beisen_host(records):
    res = resolve_apply_channel("beisen", TENANT, records[0].ats_job_id,
                                records[0].apply_channel)
    # Already canonical → trusted as-is, and re-resolving is idempotent.
    assert res.url == records[0].apply_channel
    assert res.is_embed is False
    assert canonical_apply_url("beisen", TENANT, "GUID42").endswith("jobAdId=GUID42")


def test_posted_at_is_the_real_ats_date(records):
    first = records[0]
    assert first.posted_at is not None
    # 2025-09-11T18:05:28 Beijing == 10:05:28Z.
    assert first.posted_at.astimezone(dt.timezone.utc) == dt.datetime(
        2025, 9, 11, 10, 5, 28, tzinfo=dt.timezone.utc
    )


def test_zero_date_becomes_null_never_crawl_time():
    """Beisen writes year 1 for 'never published'; a fabricated datePosted is worse
    than a missing one, so it must be NULL."""
    payload = {"Data": [dict(PAYLOAD["Data"][0],
                             PostDate="0001-01-01T00:00:00", PostDateInt=0,
                             ChangeDate="0001-01-01T00:00:00")]}
    rec = BeisenClient().parse(payload, TENANT)[0]
    assert rec.posted_at is None
    assert rec.updated_at is None


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("25K-50K 元/月", (25000, 50000, "CNY")),
        ("12K-20K 元/月", (12000, 20000, "CNY")),
        ("1-2万/月", (10000, 20000, "CNY")),
        ("面议", (None, None, None)),
        (None, (None, None, None)),
        ("", (None, None, None)),
    ],
)
def test_salary_parsed_as_published(raw, expected):
    assert BeisenClient._salary(raw) == expected


def test_monthly_salary_is_never_annualised(records):
    """25K-50K 元/月 stays 25000–50000 — no ×12/×13/×16 invention."""
    first = records[0]
    assert (first.salary_min, first.salary_max) == (25000, 50000)
    assert first.salary_currency == "CNY"


def test_location_joins_all_names(records):
    assert records[1].location == "浙江省·杭州市·滨江区"


def test_remote_hint_defaults_to_unknown(records):
    # Beisen exposes no workplace-type field; nothing may be inferred.
    assert {r.remote_hint for r in records} == {"unknown"}


def test_remote_only_when_explicitly_marked():
    payload = {"Data": [dict(PAYLOAD["Data"][0], JobAdName="远程 Python 工程师")]}
    assert BeisenClient().parse(payload, TENANT)[0].remote_hint == "remote"


@pytest.mark.asyncio
async def test_fetch_posts_and_pages(monkeypatch):
    """fetch() POSTs with DisplayFields (without which the portal omits date/salary)
    and stops when a short page arrives."""
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=PAYLOAD)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        result = await BeisenClient().fetch(client, TENANT)

    assert result.ok and result.status == 200
    assert result.count == len(PAYLOAD["Data"])
    assert len(seen) == 1  # short page → no second request
    body = seen[0]
    assert body["Category"] == ["1"]                 # 社招 only, not 校招
    assert "PostDate" in body["DisplayFields"]
    assert "Salary" in body["DisplayFields"]


@pytest.mark.asyncio
async def test_fetch_rejects_non_200():
    transport = httpx.MockTransport(lambda r: httpx.Response(503, text="nope"))
    async with httpx.AsyncClient(transport=transport) as client:
        result = await BeisenClient().fetch(client, TENANT)
    assert result.ok is False
    assert result.status == 503


@pytest.mark.asyncio
async def test_fetch_rejects_payload_without_data_array():
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"Code": 500}))
    async with httpx.AsyncClient(transport=transport) as client:
        result = await BeisenClient().fetch(client, TENANT)
    assert result.ok is False
    assert result.error == "no jobs array"
