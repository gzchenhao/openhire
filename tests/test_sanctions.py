"""Sanctions screening on the seeker's machine (reports/070). Hermetic: the lists are strings.

The load-bearing assertions: only legal-form suffixes are stripped before comparing (so
"Prince Group" never collapses to "prince"), a bilingual name is tried in both scripts, a
hit names the entry and says a name match is not a verdict, an alias hit names its primary,
and a missing list is reported as the network, never as a fact about the employer.
"""

from __future__ import annotations

from openhire.verify import employer_check, sanctions
from openhire.verify.sanctions import name_candidates, normalise, screen

SDN = (
    '36,"PRINCE HOLDING GROUP CO., LTD.","Entity","CYBER2; TCO",-0-,-0-,-0-,-0-,-0-,-0-,-0-,"Cambodia"\n'
    '99,"SOME PERSON","Individual","SDGT",-0-,-0-,-0-,-0-,-0-,-0-,-0-,-0-\n'
)
ALT = '36,1,"aka","PRINCE GROUP",-0-\n'
CONS = '500,"EXAMPLE FOREIGN BANK","Entity","CAPTA",-0-,-0-,-0-,-0-,-0-,-0-,-0-,-0-\n'
LISTS = {"texts": {"sdn": SDN, "sdn_alt": ALT, "cons": CONS, "cons_alt": ""}, "downloaded": "2026-10-11"}


def test_normalise_drops_punctuation_and_legal_forms_only():
    assert normalise("Prince Holding Group Co., Ltd.") == "prince holding group"
    assert normalise("深圳某某科技有限公司") == "深圳某某科技"
    assert normalise("Li Auto Inc.") == "li auto"
    assert normalise("Prince Group Limited") == "prince group"  # "group" is part of the name


def test_candidates_try_both_scripts_of_a_bilingual_name():
    assert name_candidates("理想汽车 Li Auto") >= {"理想汽车 li auto", "li auto", "理想汽车"}
    assert name_candidates("x") == set()  # too short to mean anything


def test_screen_reports_the_matching_entry_never_a_verdict():
    out = screen("Prince Holding Group Company Limited", lists=LISTS)
    assert out["status"] == "not_verified" and out["matches"][0]["ent_num"] == "36"
    assert "同名不等于同一主体" in out["note"] and "CYBER2" in out["note"]
    alias = screen("Prince Group", lists=LISTS)
    assert alias["status"] == "not_verified" and alias["matches"][0]["alias_of"] == "PRINCE HOLDING GROUP CO., LTD."
    clean = screen("理想汽车 Li Auto", lists=LISTS)
    assert clean["status"] == "verified" and "2026-10-11" in clean["note"]
    assert screen("x", lists=LISTS)["status"] == "not_applicable"


def test_missing_lists_are_named_as_the_network_not_the_employer(monkeypatch):
    monkeypatch.setattr(sanctions, "load_lists", lambda allow_network=True: {"error": "network"})
    out = screen("Prince Group")
    assert out["status"] == "unavailable" and out["reason"] == "network" and "不是雇主" in out["note"]
    monkeypatch.setattr(sanctions, "load_lists", lambda allow_network=True: {"error": "offline"})
    assert screen("Prince Group", allow_network=False)["reason"] == "offline"


def test_load_lists_fetches_each_file_once_a_day(monkeypatch, tmp_path):
    monkeypatch.setattr(sanctions.config, "CLIENT_HOME", tmp_path)
    calls: list[str] = []

    class R:
        status_code = 200
        text = '1,"A","Entity","P",-0-\n'

    monkeypatch.setattr(sanctions.checks, "_get", lambda url, timeout=None: calls.append(url) or R())
    first = sanctions.load_lists()
    assert set(first["texts"]) == set(sanctions.FILES) and len(calls) == 4 and first["downloaded"]
    sanctions.load_lists()
    assert len(calls) == 4  # served from the daily cache, no second GET
    monkeypatch.setattr(sanctions.checks, "_get", lambda url, timeout=None: None)
    assert "texts" in sanctions.load_lists(allow_network=False)  # offline, cache present


def test_checklist_carries_the_sanctions_item_with_its_matches(monkeypatch):
    monkeypatch.setattr(sanctions, "load_lists", lambda allow_network=True: LISTS)
    res = employer_check.build_checklist(
        query={"company": "Prince Group"}, index_facts=None, known_not_indexed=None, domain=None,
        run_network=True, register_fn=lambda name: {"status": "pending_user", "note": "x"},
    )
    by = {i["id"]: i for i in res["checks"]}
    assert by["sanctions_screen"]["status"] == "not_verified" and by["sanctions_screen"]["matches"][0]["ent_num"] == "36"
    assert by["sanctions_screen"]["lists_downloaded"] == "2026-10-11"
