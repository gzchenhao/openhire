"""Client-side state tests — fingerprint, local repo scan, receipts.

Uses the temp OPENHIRE_HOME from conftest; each test starts from a clean home.
"""

from __future__ import annotations

import pytest

from openhire import client


@pytest.fixture(autouse=True)
def clean_home():
    for p in (client.fingerprint_path(), client.receipts_path()):
        if p.exists():
            p.unlink()
    yield
    for p in (client.fingerprint_path(), client.receipts_path()):
        if p.exists():
            p.unlink()


def test_fingerprint_id_format():
    fid = client.new_fingerprint_id()
    assert fid.startswith("#") and len(fid) == 5  # '#' + 4 hex


def test_fingerprint_roundtrip():
    fp = client.Fingerprint(id="#a3f9", skills=["rust", "k8s"], created_at="2026-07-10")
    client.save_fingerprint(fp)
    loaded = client.load_fingerprint()
    assert loaded.id == "#a3f9" and loaded.skills == ["rust", "k8s"]


def test_load_or_create_mints_anonymous():
    assert client.load_fingerprint() is None
    fp = client.load_or_create_fingerprint()
    assert fp.id.startswith("#")
    assert client.load_fingerprint().id == fp.id  # persisted


def test_receipts_append_and_load():
    assert client.load_receipts() == []
    client.append_receipt({"receipt_id": "r_1", "company": "Acme"})
    client.append_receipt({"receipt_id": "r_2", "company": "Beta"})
    rs = client.load_receipts()
    assert [r["receipt_id"] for r in rs] == ["r_1", "r_2"]


def test_scan_repos_derives_skills_locally(tmp_path):
    # A tiny fake repo: Python + Rust files + a manifest naming a known dependency.
    repo = tmp_path / "proj"
    (repo / "svc").mkdir(parents=True)
    (repo / "svc" / "main.py").write_text("import torch\nprint('hi')\n", encoding="utf-8")
    (repo / "svc" / "app.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "core").mkdir()
    (repo / "core" / "lib.rs").write_text("fn main() {}\n", encoding="utf-8")
    (repo / "requirements.txt").write_text("torch\nlangchain\nfastapi\n", encoding="utf-8")

    skills, lang_pct, repos = client.scan_repos(repo)
    assert "python" in skills
    assert "pytorch" in skills   # torch → pytorch
    assert "rag" in skills       # langchain → rag
    assert "python" in lang_pct and lang_pct["python"] > 0
    assert repos >= 1


def test_scan_skips_vendor_dirs(tmp_path):
    repo = tmp_path / "proj"
    (repo / "node_modules" / "pkg").mkdir(parents=True)
    (repo / "node_modules" / "pkg" / "junk.py").write_text("x=1", encoding="utf-8")
    (repo / "src").mkdir()
    (repo / "src" / "a.rs").write_text("fn main(){}", encoding="utf-8")
    skills, lang_pct, _ = client.scan_repos(repo)
    # node_modules content must be ignored → no python from the junk file.
    assert "python" not in lang_pct
    assert "rust" in skills
