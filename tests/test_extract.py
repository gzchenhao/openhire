"""Extractor tests — skills, remote policy, salary (no inference in v0.1)."""

from __future__ import annotations

from openhire.ats.base import JobRecord
from openhire.pipeline.extract import (
    HeuristicExtractor,
    canonicalize_skills,
    extract_salary_from_text,
    extract_skills,
)


def test_canonicalize_skills_maps_aliases():
    # LLMs return free-form; canonicalization keeps search matching consistent.
    assert canonicalize_skills(["Kubernetes", "Golang", "PostgreSQL"]) == [
        "k8s", "go", "postgres"
    ]
    assert canonicalize_skills(["k8s", "kubernetes"]) == ["k8s"]  # de-duped
    assert canonicalize_skills(["Rust", "unknown-thing"]) == ["rust", "unknown-thing"]


def _job(title, desc, **kw):
    return JobRecord(
        ats_job_id="x", title=title, description_raw=desc,
        apply_channel="https://e.co/apply", **kw,
    )


def test_skills_are_lowercase_normalized():
    skills = extract_skills("Senior Rust Engineer — Kubernetes, RAG, CUDA")
    assert "rust" in skills and "k8s" in skills and "rag" in skills and "cuda" in skills
    assert all(s == s.lower() for s in skills)


def test_remote_hint_wins():
    ex = HeuristicExtractor().extract(_job("Eng", "desc", remote_hint="hybrid"))
    assert ex.remote_policy == "hybrid"


def test_remote_from_text_when_no_hint():
    ex = HeuristicExtractor().extract(_job("Eng", "This is a fully remote position."))
    assert ex.remote_policy == "remote"


def test_structured_salary_preferred():
    ex = HeuristicExtractor().extract(
        _job("Eng", "no numbers here", salary_min=180000, salary_max=240000,
             salary_currency="USD")
    )
    assert (ex.salary_min, ex.salary_max, ex.salary_currency) == (180000, 240000, "USD")


def test_salary_parsed_from_text():
    lo, hi, cur = extract_salary_from_text("The range is $180,000 - $240,000 per year.")
    assert lo == 180000 and hi == 240000 and cur == "USD"


def test_salary_k_notation():
    lo, hi, cur = extract_salary_from_text("Comp: $180k–$240k")
    assert lo == 180000 and hi == 240000


def test_no_salary_returns_none_no_inference():
    lo, hi, cur = extract_salary_from_text("A great team with big impact.")
    assert (lo, hi, cur) == (None, None, None)


def test_salary_never_inferred_flag():
    # Even with structured comp, salary_inferred must be decided by the pipeline as
    # False in v0.1; the extractor itself never sets an inferred flag.
    ex = HeuristicExtractor().extract(_job("Eng", "text", salary_min=100000, salary_max=150000))
    assert not hasattr(ex, "salary_inferred")
