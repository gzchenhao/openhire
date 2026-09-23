"""Extractor tests — skills, remote policy, salary (no inference in v0.1)."""

from __future__ import annotations

import pytest

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


def test_no_skills_from_a_title_when_the_description_is_empty():
    """An employer that gave us no JD gets no tags: 'Rust Engineer' + '' must not become
    ['rust'], because that tag would read as something we saw in a description."""
    assert HeuristicExtractor().extract(_job("Senior Rust / CUDA Engineer", "")).skills == []
    assert HeuristicExtractor().extract(_job("Senior Rust Engineer", "   \n ")).skills == []
    # With any real description, the title still counts as context, as before.
    assert "rust" in HeuristicExtractor().extract(_job("Senior Rust Engineer", "Build things.")).skills


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


# --- no JD, no model call (every LLM backend) --------------------------------------------
class _ModelCalled(BaseException):
    """Deliberately NOT an Exception: every LLM `extract` degrades to the heuristic on any
    Exception, which would turn a missing guard into a silently passing test."""


class _Raiser:
    """Stands in for the provider client: any call is a test failure."""

    def __getattr__(self, name):
        raise _ModelCalled(f"the model was called ({name}) for a posting with no JD")

    def post(self, *a, **k):
        raise _ModelCalled("the model was called for a posting with no JD")


def _anthropic():
    from openhire.pipeline.extract import AnthropicExtractor
    ex = AnthropicExtractor.__new__(AnthropicExtractor)  # skip the SDK client construction
    ex._client, ex._model, ex._fallback = _Raiser(), "m", HeuristicExtractor()
    return ex


def _deepseek():
    from openhire.pipeline.extract import DeepSeekExtractor
    ex = DeepSeekExtractor("k", "https://example.invalid", "m")
    ex._client = _Raiser()
    return ex


def _glm():
    from openhire.pipeline.extract import GLMExtractor
    ex = GLMExtractor("k", "https://example.invalid", "m")
    ex._client = _Raiser()
    return ex


@pytest.mark.parametrize("make", [_anthropic, _deepseek, _glm], ids=["anthropic", "deepseek", "glm"])
@pytest.mark.parametrize("desc", ["", "   \n\t "], ids=["empty", "whitespace"])
def test_every_llm_extractor_short_circuits_on_an_empty_description(make, desc):
    """A posting with no JD never reaches a model: the answer would be inferred from the
    title and paid for. The heuristic answers instead (no skills) and signs the row."""
    ex = make()
    out = ex.extract(_job("Senior Rust / CUDA Engineer", desc, remote_hint="onsite"))
    assert out.skills == []
    assert out.extractor == "heuristic"
    assert out.remote_policy == "onsite"  # the ATS field still counts
    # The stub really bites: with a JD the same extractor does reach the model.
    with pytest.raises(_ModelCalled):
        ex.extract(_job("Senior Rust / CUDA Engineer", "Rust and CUDA required.", remote_hint="onsite"))


def test_remote_policy_is_not_read_off_a_bare_title():
    """With no JD the only text is the title; "Remote Rust Engineer" is a title, not a
    workplace policy. The ATS-native fields (remote_hint, location) still decide."""
    assert HeuristicExtractor().extract(_job("Remote-first Rust Engineer", "")).remote_policy == "unknown"
    assert HeuristicExtractor().extract(_job("Hybrid Rust Engineer", " ")).remote_policy == "unknown"
    assert HeuristicExtractor().extract(
        _job("Rust Engineer", "", location="Remote - US")
    ).remote_policy == "remote"
    assert HeuristicExtractor().extract(
        _job("Rust Engineer", "", remote_hint="hybrid")
    ).remote_policy == "hybrid"
    # With a JD, the text (title included, as before) is still read.
    assert HeuristicExtractor().extract(
        _job("Rust Engineer", "This is a fully remote position.")
    ).remote_policy == "remote"
