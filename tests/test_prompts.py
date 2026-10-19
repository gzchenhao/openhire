"""Built-in prompts (0.8.14): one-click templates for the questions seekers ask.

What these pin: the five templates are listed with titles and argument descriptions; each
renders in Chinese when the user typed Chinese and in English otherwise; every rendering
carries the privacy rule; every tool a template tells the assistant to call exists; no
template uses a dash the copy rules forbid; and the server instructions tell the assistant
to offer add_employer and the portal link itself, so a seeker never needs tool names."""

from __future__ import annotations

import asyncio
import re

import pytest

from openhire import prompts
from openhire.mcp_server import mcp

NAMES = ["job_radar", "track_employer", "vet_employer", "radar_check", "new_this_week"]

# Identifiers a template may mention that are argument names or field values, not tools.
NOT_TOOLS = {"job_id", "posting_text", "board_url", "date_signal", "not_reported_by_ats", "pending_user"}

ZH_ARGS = {
    "job_radar": {"role": "感知算法工程师", "location": "上海", "skills": "点云, BEV"},
    "track_employer": {"employer": "智元机器人"},
    "vet_employer": {"employer": "某某科技", "posting": "高薪打字员，包机票"},
    "radar_check": {"fingerprint": "#a3f9-k2p7-x8q1"},
    "new_this_week": {"role": "规控", "location": "深圳"},
}
EN_ARGS = {
    "job_radar": {"role": "robotics software engineer", "location": "remote"},
    "track_employer": {"employer": "https://jobs.lever.co/okx"},
    "vet_employer": {"employer": "Acme Robotics", "posting": "acme:123"},
    "radar_check": {},
    "new_this_week": {},
}


def _render(name: str, args: dict) -> str:
    res = asyncio.run(mcp.get_prompt(name, args))
    return "\n".join(m.content.text for m in res.messages)


def _tools() -> set[str]:
    return {t.name for t in asyncio.run(mcp.list_tools())}


def test_the_five_templates_are_listed_with_titles_and_argument_help():
    listed = {p.name: p for p in asyncio.run(mcp.list_prompts())}
    assert list(listed) == NAMES
    for p in listed.values():
        assert p.title and "·" in p.title          # Chinese · English, so either reader can pick
        assert p.description
        for a in p.arguments or []:
            assert a.description, f"{p.name}.{a.name} has no description"
    assert [a.name for a in listed["job_radar"].arguments if a.required] == ["role"]
    assert not any(a.required for a in listed["new_this_week"].arguments)


@pytest.mark.parametrize("name", NAMES)
def test_language_follows_what_the_user_typed(name):
    zh, en = _render(name, ZH_ARGS[name]), _render(name, EN_ARGS[name])
    assert re.search(r"[一-鿿]", zh)
    if name != "radar_check":                     # the one template with no words to go by is bilingual
        assert not re.search(r"[一-鿿]{4,}", en.replace("BOSS直聘", "").replace("北森", ""))


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("lang", ["zh", "en"])
def test_every_template_keeps_the_privacy_rule_and_names_only_real_tools(name, lang):
    text = _render(name, (ZH_ARGS if lang == "zh" else EN_ARGS)[name])
    if name == "radar_check":
        assert "check_watches" in text            # nothing of the user's is asked for at all
    else:
        assert (prompts.PRIVACY_ZH in text) or (prompts.PRIVACY_EN in text)
    named = set(re.findall(r"\b[a-z]+(?:_[a-z]+)+\b", text)) - NOT_TOOLS
    assert named, "a template that names no tool gives the assistant nothing to do"
    assert named <= _tools(), f"{name} names tools that do not exist: {named - _tools()}"
    assert "—" not in text and "——" not in text   # copy rule 3: no dashes


def test_track_employer_walks_the_whole_path_without_tool_names_from_the_user():
    text = _render("track_employer", {"employer": "OKX"})
    for step in ("search_jobs", "read_board", "add_employer", "watch_intent", "board_url"):
        assert step in text
    assert "Feishu" in text                       # the portal-link branch is part of the path


def test_vet_employer_routes_an_id_and_a_pasted_posting_to_the_right_argument():
    assert "job_id" in _render("vet_employer", {"employer": "Acme", "posting": "acme:123"})
    assert "posting_text" in _render("vet_employer", {"employer": "Acme", "posting": "We pay $500/day, no experience"})
    assert "不是判决" in _render("vet_employer", {"employer": "某某科技"})


def test_instructions_tell_the_assistant_to_offer_the_next_step_itself():
    text = " ".join((mcp.instructions or "").split())
    assert "never has to know these tool names" in text
    assert "add_employer, then watch_intent" in text
    assert "give the user that portal link" in text
    assert "Workday" in text
