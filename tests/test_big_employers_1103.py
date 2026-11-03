"""reports/135: Lever's EU instance, and the big employers added on 2026-11-03."""

from openhire.ats import boards
from openhire.ats.base import canonical_apply_url
from openhire.ats.lever import LeverClient
from openhire.seed import candidates, not_indexed, sectors


def test_lever_eu_board_url_maps_to_the_eu_api():
    assert boards.detect_board("https://jobs.eu.lever.co/mobileye") == ("lever", "eu.mobileye")
    assert boards.detect_board("https://api.eu.lever.co/v0/postings/mobileye?mode=json") == ("lever", "eu.mobileye")
    assert boards.detect_board("https://jobs.lever.co/zoox") == ("lever", "zoox")
    c = LeverClient.__new__(LeverClient)
    assert c.endpoint("eu.mobileye") == "https://api.eu.lever.co/v0/postings/mobileye?mode=json"
    assert c.endpoint("zoox") == "https://api.lever.co/v0/postings/zoox?mode=json"
    assert canonical_apply_url("lever", "eu.mobileye", "abc") == "https://jobs.eu.lever.co/mobileye/abc"


def test_new_seeds_and_sectors():
    slugs = {c.slug: c for c in candidates.all_candidates()}
    assert slugs["mobileye"].tenant == "eu.mobileye" and slugs["gatik"].tenant == "gatikaiinc"
    assert slugs["nvidia"].vendor == "workday"
    assert sectors.COMPANY_SECTOR["mobileye"] == "autonomous_driving"
    assert sectors.COMPANY_SECTOR["nvidia"] == "ai_infra"


def test_unreadable_big_employers_are_in_the_portal_directory():
    ids = {e.id for e in not_indexed.NOT_INDEXED}
    for i in ("tesla", "baidu-apollo", "huawei", "xpeng-motors", "byd", "xiaomi-ev", "didi-autonomous", "meituan", "deepmind"):
        assert i in ids, i
