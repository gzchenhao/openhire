"""Moka (`app.mokahr.com/apply/<org>/<siteId>`) adapter — hermetic, no network.

Every fixture is a real capture taken on 2026-09-02 (see reports/020):

  * `moka_portal_page.html`             — a live portal page, trimmed to the `#init-data`
                                          element the client actually reads.
  * `moka_portal_absent.html`           — a slug that does not exist.
  * `moka_portal_retired.html`          — a real org whose portal was shut down (毫末智行).
  * `moka_robotera_jobs_encrypted.json` — an untouched AES envelope off the wire, so the
                                          transport decoder is pinned to vendor output.
  * `moka_robotera_page.json`           — decoded list + per-job detail (星动纪元).
  * `moka_robosense_page.json`          — same for 速腾聚创, which publishes pay.

The load-bearing assertions are the ones this vendor makes easy to get wrong:
  * HTTP 200 is *not* proof a tenant exists — absent and retired portals answer 200 too;
  * `posted_at` is the employer's own 发布日期 and is never backfilled with the crawl time;
  * a monthly CNY salary is stored as published and never annualised;
  * `apply_channel` deep-links into the hash route, which is the only form that works.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import pathlib

import httpx
import pytest

from openhire.ats import get_client
from openhire.ats._aes import decrypt_cbc
from openhire.ats.base import canonical_apply_url, resolve_apply_channel
from openhire.ats.moka import MokaClient

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
ROBOTERA = json.loads((FIXTURES / "moka_robotera_page.json").read_text(encoding="utf-8"))
ROBOSENSE = json.loads((FIXTURES / "moka_robosense_page.json").read_text(encoding="utf-8"))
ENCRYPTED = json.loads(
    (FIXTURES / "moka_robotera_jobs_encrypted.json").read_text(encoding="utf-8")
)
PORTAL = (FIXTURES / "moka_portal_page.html").read_text(encoding="utf-8")
PORTAL_ABSENT = (FIXTURES / "moka_portal_absent.html").read_text(encoding="utf-8")
PORTAL_RETIRED = (FIXTURES / "moka_portal_retired.html").read_text(encoding="utf-8")

TENANT = "robotera/163877"


@pytest.fixture()
def records():
    return MokaClient().parse(ROBOTERA, TENANT)


# --- registry -----------------------------------------------------------------
def test_registered_as_a_vendor():
    assert isinstance(get_client("moka"), MokaClient)
    assert get_client("moka").vendor == "moka"


def test_tenant_is_the_org_and_site_pair():
    assert MokaClient._split("robotera/163877") == ("robotera", "163877")
    with pytest.raises(ValueError):
        MokaClient._split("robotera")


def test_careers_url_is_the_public_portal():
    assert MokaClient().careers_url(TENANT) == "https://app.mokahr.com/apply/robotera/163877"


# --- FIPS-197 vectors for the pure-Python AES ---------------------------------
@pytest.mark.parametrize(
    "key_hex, ct_hex",
    [
        ("000102030405060708090a0b0c0d0e0f", "69c4e0d86a7b0430d8cdb78070b4c55a"),
        ("000102030405060708090a0b0c0d0e0f1011121314151617",
         "dda97ca4864cdfe06eaf70a0ec0d7191"),
        ("000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f",
         "8ea2b7ca516745bfeafc49904b496089"),
    ],
)
def test_aes_matches_fips197_vectors(key_hex, ct_hex):
    """FIPS-197 appendix C: one ECB block == CBC with a zero IV and no padding."""
    from openhire.ats._aes import _decrypt_block, _expand_key

    plain = _decrypt_block(bytes.fromhex(ct_hex), _expand_key(bytes.fromhex(key_hex)))
    assert plain.hex() == "00112233445566778899aabbccddeeff"


def test_cbc_rejects_bad_padding_rather_than_guessing():
    key, iv = b"0123456789abcdef", b"fedcba9876543210"
    with pytest.raises(ValueError):
        decrypt_cbc(b"\x00" * 16, key, iv)
    with pytest.raises(ValueError):
        decrypt_cbc(b"\x00" * 15, key, iv)  # not a whole block


# --- transport ----------------------------------------------------------------
def test_unwraps_a_real_encrypted_envelope():
    """The key ships inside the response and the IV comes off the portal page."""
    payload = dict(ENCRYPTED["response"], __iv__=ENCRYPTED["iv"])
    assert set(ENCRYPTED["response"]) == {"data", "necromancer"}
    data = MokaClient._unwrap(payload)
    assert isinstance(data["jobs"], list) and data["jobs"]
    assert all(j.get("id") for j in data["jobs"])


def test_unwrap_passes_plain_json_straight_through():
    assert MokaClient._unwrap({"jobs": []}) == {"jobs": []}


def test_unwrap_without_an_iv_fails_loudly():
    with pytest.raises(ValueError):
        MokaClient._unwrap({"data": base64.b64encode(b"x" * 16).decode(), "necromancer": "k" * 16})


# --- portal page --------------------------------------------------------------
def test_init_data_yields_org_and_iv():
    init = MokaClient.parse_init_data(PORTAL)
    assert init["org"]["id"] == "robotera"
    assert init["aesIv"] and len(init["aesIv"]) == 16


@pytest.mark.parametrize("page", [PORTAL_ABSENT, PORTAL_RETIRED])
def test_absent_and_retired_portals_carry_no_org(page):
    """Moka answers HTTP 200 for a bogus or shut-down slug, so 200 is never the test."""
    assert not MokaClient.parse_init_data(page).get("org")


# --- parsing ------------------------------------------------------------------
def test_parses_every_row(records):
    assert len(records) == len(ROBOTERA["jobs"])
    assert [r.title for r in records] == [j["title"] for j in ROBOTERA["jobs"]]


def test_five_protocol_fields_present(records):
    for r in records:
        assert r.ats_job_id and r.title
        assert r.description_raw  # merged in from the per-job detail call
        assert r.apply_channel.startswith("https://")


def test_apply_channel_deep_links_via_the_hash_route(records):
    for r, raw in zip(records, ROBOTERA["jobs"]):
        assert r.ats_job_id == raw["id"]
        assert r.apply_channel == f"https://app.mokahr.com/apply/{TENANT}#/job/{raw['id']}"


def test_apply_channel_is_on_the_employers_own_moka_host(records):
    for r in records:
        assert r.apply_channel.startswith("https://app.mokahr.com/apply/robotera/163877#/job/")
    resolution = resolve_apply_channel("moka", TENANT, "abc", "https://example.com/careers")
    assert resolution.used_fallback and resolution.is_embed
    assert resolution.url == canonical_apply_url("moka", TENANT, "abc")


def test_posted_at_is_the_employers_published_date(records):
    for r, raw in zip(records, ROBOTERA["jobs"]):
        assert r.posted_at is not None
        # 发布日期 as the portal renders it, read as Beijing time.
        expected = dt.datetime.fromisoformat(raw["publishedAt"]).replace(
            tzinfo=dt.timezone(dt.timedelta(hours=8))
        )
        assert r.posted_at == expected.astimezone(dt.timezone.utc)


def test_posted_at_falls_back_to_opened_at_then_null():
    client = MokaClient()
    (only_opened,) = client.parse(
        {"jobs": [{"id": "a", "title": "t", "openedAt": "2026-07-05T00:00"}]}, TENANT
    )
    assert only_opened.posted_at == dt.datetime(2026, 7, 4, 16, 0, tzinfo=dt.timezone.utc)

    (undated,) = client.parse({"jobs": [{"id": "b", "title": "t"}]}, TENANT)
    assert undated.posted_at is None  # never the crawl time — P0-2


@pytest.mark.parametrize("raw", ["0001-01-01T00:00", "not a date", "", None])
def test_unusable_dates_become_null_never_crawl_time(raw):
    assert MokaClient._date(raw) is None


def test_monthly_salary_is_never_annualised():
    records = MokaClient().parse(ROBOSENSE, "robosense/77883")
    priced = [r for r in records if r.salary_min]
    assert priced, "the robosense fixture is expected to publish pay"
    for r in priced:
        assert r.salary_currency == "CNY"
        assert r.salary_period == "monthly"
        assert r.salary_min <= 100_000  # a monthly figure, not a x12 annualisation


@pytest.mark.parametrize(
    "raw, expected",
    [
        ({"minSalary": 35, "maxSalary": 57}, (35000, 57000)),        # 千元/月 shorthand
        ({"minSalary": 35000, "maxSalary": 60000}, (35000, 60000)),  # already yuan
        ({"minSalary": 35, "maxSalary": 60000}, (None, None)),       # mixed — unreadable
        ({"minSalary": 0, "maxSalary": 0}, (None, None)),
        ({"minSalary": 57, "maxSalary": 35}, (None, None)),          # inverted
        ({}, (None, None)),
        # 全职 keeps the shorthand; 实习/兼职 quote a DAY rate in the same field, which this
        # schema cannot express — 150-250 元/天 must never become 150K-250K 元/月.
        ({"minSalary": 20, "maxSalary": 40, "commitment": "全职"}, (20000, 40000)),
        ({"minSalary": 150, "maxSalary": 250, "commitment": "实习"}, (None, None)),
        ({"minSalary": 150, "maxSalary": 250, "commitment": "兼职"}, (None, None)),
    ],
)
def test_salary_parsed_as_published(raw, expected):
    assert MokaClient._salary(raw) == expected


def test_internship_day_rates_are_never_read_as_monthly_pay():
    """freetech's 实习生 rows read 150-250 元/天; x1000 would invent a 150K/month intern."""
    intern = {"id": "i", "title": "雷达数据处理算法实习生", "commitment": "实习",
              "minSalary": 200, "maxSalary": 250}
    (rec,) = MokaClient().parse({"jobs": [intern]}, TENANT)
    assert rec.salary_min is None and rec.salary_max is None
    assert rec.salary_currency is None


def test_both_salary_magnitudes_are_present_in_the_fixture():
    """The same employer files 35–57 and 35000–60000; both must land on the same band."""
    bands = {MokaClient._salary(d) for d in ROBOSENSE["details"].values()}
    assert (35000, 57000) in bands and (35000, 60000) in bands


def test_location_is_province_and_city():
    records = MokaClient().parse(ROBOSENSE, "robosense/77883")
    assert any(r.location and "·" in r.location for r in records)


def test_remote_hint_defaults_to_unknown(records):
    assert all(r.remote_hint == "unknown" for r in records)


def test_remote_only_when_explicitly_marked():
    (rec,) = MokaClient().parse({"jobs": [{"id": "x", "title": "算法工程师（远程）"}]}, TENANT)
    assert rec.remote_hint == "remote"


def test_a_job_without_a_detail_still_becomes_a_record():
    """A failed detail call must not drop the job — that would read as a delisting."""
    (rec,) = MokaClient().parse({"jobs": [{"id": "z", "title": "t"}], "details": {}}, TENANT)
    assert rec.ats_job_id == "z" and rec.description_raw == ""


# --- fetch --------------------------------------------------------------------
class _FakeTransport(httpx.AsyncBaseTransport):
    """Replays the captured portal page and encrypted API responses."""

    def __init__(self, portal: str, jobs: dict, details: dict):
        self.portal, self.jobs, self.details = portal, jobs, details
        self.calls: list[str] = []

    async def handle_async_request(self, request):
        self.calls.append(str(request.url))
        if "/api/outer/ats-apply/website/jobs" in request.url.path:
            body = json.loads(request.content)
            assert body["site"] == "social" and body["orgId"] and body["siteId"]
            page = body["offset"] // body["limit"]
            payload = {"jobs": self.jobs} if page == 0 else {"jobs": []}
            return httpx.Response(200, json=payload)
        if "/api/outer/ats-apply/website/job" in request.url.path:
            job_id = json.loads(request.content)["jobId"]
            return httpx.Response(200, json=self.details.get(job_id, {}))
        return httpx.Response(200, text=self.portal)


async def _fetch(portal, jobs, details, tenant=TENANT):
    transport = _FakeTransport(portal, jobs, details)
    async with httpx.AsyncClient(transport=transport) as client:
        return await MokaClient().fetch(client, tenant), transport


@pytest.mark.asyncio
async def test_fetch_reads_the_portal_then_the_roster_then_each_detail():
    result, transport = await _fetch(PORTAL, ROBOTERA["jobs"], ROBOTERA["details"])
    assert result.ok and result.count == len(ROBOTERA["jobs"])
    assert transport.calls[0].endswith("/apply/robotera/163877")
    assert sum("website/job" in c and "website/jobs" not in c for c in transport.calls) == len(
        ROBOTERA["jobs"]
    )
    assert all(r.description_raw for r in result.records)


@pytest.mark.asyncio
async def test_fetch_drops_closed_postings():
    jobs = [dict(ROBOTERA["jobs"][0], status="closed"), ROBOTERA["jobs"][1]]
    result, _ = await _fetch(PORTAL, jobs, ROBOTERA["details"])
    assert result.ok and result.count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("page", [PORTAL_ABSENT, PORTAL_RETIRED])
async def test_fetch_rejects_a_200_portal_with_no_org(page):
    result, transport = await _fetch(page, ROBOTERA["jobs"], ROBOTERA["details"])
    assert not result.ok and result.status == 200
    assert "org" in (result.error or "")
    assert len(transport.calls) == 1  # gave up before touching the API


@pytest.mark.asyncio
async def test_fetch_rejects_a_malformed_tenant():
    async with httpx.AsyncClient(transport=_FakeTransport(PORTAL, [], {})) as client:
        result = await MokaClient().fetch(client, "robotera")
    assert not result.ok and "<org>/<siteId>" in (result.error or "")
