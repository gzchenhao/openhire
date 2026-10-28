"""The connect guide (0.8.30, reports/100): the answer to "the first connection is the hard
part" from a tester who came in through VS Code and found no instructions for it. One page,
pick your assistant, only its steps and the one block to paste; no postings on it."""

from __future__ import annotations

import re
from pathlib import Path

from starlette.testclient import TestClient

from openhire import hosted
from openhire.mcp_server import mcp

ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "docs" / "connect.html").read_text(encoding="utf-8")


def _readme_block(start: str) -> list[str]:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    block = readme.split("```text\n" + start, 1)[1].split("```", 1)[0]
    return [line for line in (start + block).splitlines() if line.strip()]


def test_served_identical_to_docs_and_linked_from_both_homes():
    client = TestClient(hosted.build_app(mcp))
    r = client.get("/connect")
    assert r.status_code == 200 and r.text == PAGE
    assert client.get("/connect.html").text == PAGE
    assert (ROOT / "src" / "openhire" / "pages" / "connect.html").read_text(encoding="utf-8") == PAGE, \
        "docs/connect.html and src/openhire/pages/connect.html differ: copy one over the other"
    assert "/connect" in client.get("/").text
    assert "connect.html" in (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
    assert "connect.html" in (ROOT / "docs" / "checklist.html").read_text(encoding="utf-8")


def test_carries_the_one_block_prompts_verbatim_from_the_readme():
    for line in _readme_block("帮我装一个 MCP 服务"):
        assert line in PAGE, line
    for line in _readme_block("Install an MCP server for me"):
        assert line in PAGE, line


def test_names_every_assistant_and_gives_each_its_own_path():
    for name in ("ChatGPT", "Claude", "豆包", "DeepSeek", "Cursor", "WorkBuddy", "VS Code", "TRAE", "Cherry Studio"):
        assert name in PAGE, name
    assert "https://openhire-vlny.onrender.com/mcp" in PAGE          # ChatGPT, nothing to install
    assert "http://127.0.0.1:8000/mcp" in PAGE                       # 豆包
    assert ".vscode/mcp.json" in PAGE and "vscode:mcp/install?" in PAGE
    assert "cursor.com/install-mcp" in PAGE and "releases/latest" in PAGE
    assert PAGE.count('data-client="vscode"') >= 2                 # zh and en sections and buttons
    assert "astral.sh/uv/install.ps1" in PAGE and "astral.sh/uv/install.sh" in PAGE
    assert "doctor" in PAGE


def test_bilingual_with_chinese_first_and_the_same_footer_as_the_other_pages():
    assert 'data-set="zh"' in PAGE and 'class="lang-en"' in PAGE
    assert PAGE.index('class="lang-zh"') < PAGE.index('class="lang-en"')
    assert "checklist_feedback.yml" in PAGE and "雇主认领入口" in PAGE and "employer_claim.yml" in PAGE
    assert "——" not in PAGE                                         # copy rule 3
    assert not re.search(r"\b0\.8\.\d+\b", PAGE), "no version number on the page (it would go stale)"
