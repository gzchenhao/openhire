"""GLM backend — provider quirks, provenance, rate-limit handling.

Everything here is offline: the HTTP layer is stubbed, so no key and no network are
needed. What is being locked down is the behaviour the live probe on 2026-08-31 found:
  * the glm-5.3 family reasons before answering, so a small max_tokens returns an EMPTY
    string instead of an error — the floor of 1024 must not silently regress;
  * with thinking disabled, glm-5.3-flash wraps its JSON in a ```json fence;
  * a GLM-written row must be stamped 'glm', never 'deepseek' — data lineage is not faked;
  * two LLM backends must not re-extract each other's rows.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from openhire import config
from openhire.db import Job, init_db, session_scope
from openhire.db.models import Company
from openhire.pipeline import rebuild
from openhire.pipeline.extract import (
    LLM_SOURCES,
    GLMExtractor,
    RateLimited,
    ExtractionResult,
    make_glm_extractor,
    parse_json_object,
)
from openhire.ats.base import JobRecord

UTC = dt.timezone.utc


# --- tolerant JSON parsing ----------------------------------------------------
def test_parse_json_object_strips_fence():
    assert parse_json_object('```json\n{"skills": ["rust"]}\n```') == {"skills": ["rust"]}


def test_parse_json_object_accepts_bare_json():
    assert parse_json_object('{"skills": []}') == {"skills": []}


def test_parse_json_object_recovers_from_surrounding_prose():
    got = parse_json_object('Sure!\n```\n{"role_family": "sales"}\n```\nHope that helps.')
    assert got == {"role_family": "sales"}


def test_parse_json_object_rejects_non_object():
    with pytest.raises((ValueError, TypeError)):
        parse_json_object("[1, 2, 3]")


# --- request shape ------------------------------------------------------------
def _glm() -> GLMExtractor:
    return GLMExtractor("dummy-key", "https://example.invalid/api/coding/paas/v4", "glm-5.3-flash")


def test_glm_disables_thinking_and_keeps_a_large_token_budget():
    payload = _glm()._payload("sys", "user", 1024)
    assert payload["thinking"] == {"type": "disabled"}
    # Reasoning tokens are charged against max_tokens BEFORE any content is emitted.
    assert payload["max_tokens"] >= 1024
    # The fence-tolerant parser is the guarantee; response_format only costs prompt tokens.
    assert "response_format" not in payload


def test_glm_extraction_and_role_family_both_use_the_large_budget():
    ext = _glm()
    assert ext._max_tokens >= 1024
    assert ext._rf_max_tokens >= 1024


def test_glm_url_targets_the_coding_endpoint():
    # The standard /api/paas/v4 path rejects coding-plan keys with error 1113.
    assert "/api/coding/paas/v4/chat/completions" in _glm()._url
    assert "/api/coding/paas/v4" in config.GLM_BASE_URL


def test_glm_is_stamped_as_its_own_source():
    assert _glm().name == "glm"
    assert "glm" in LLM_SOURCES and "deepseek" in LLM_SOURCES


def test_make_glm_extractor_requires_key(monkeypatch):
    monkeypatch.setattr(config, "ZHIPU_API_KEY", None)
    with pytest.raises(RuntimeError):
        make_glm_extractor()


# --- HTTP behaviour -----------------------------------------------------------
class _Resp:
    def __init__(self, status: int, body: dict):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _Http:
    def __init__(self, resp: _Resp):
        self._resp = resp
        self.calls = 0

    def post(self, url, json=None):
        self.calls += 1
        return self._resp


def _stub(ext, resp: _Resp) -> _Http:
    http = _Http(resp)
    ext._http = lambda: http
    return http


def test_glm_429_raises_rate_limited():
    ext = _glm()
    _stub(ext, _Resp(429, {"error": {"code": "1302"}}))
    with pytest.raises(RateLimited):
        ext.extract_with_usage(
            JobRecord(ats_job_id="1", title="t", description_raw="d",
                      apply_channel="https://x", location=None, remote_hint=None)
        )


def test_glm_parses_a_fenced_reply_end_to_end():
    ext = _glm()
    _stub(ext, _Resp(200, {
        "choices": [{"message": {"content": '```json\n{"skills":["C++","Kubernetes"],'
                                            '"remote_policy":"onsite"}\n```'}}],
        "usage": {"prompt_tokens": 68, "completion_tokens": 34},
    }))
    res, pin, pout = ext.extract_with_usage(
        JobRecord(ats_job_id="1", title="嵌入式工程师", description_raw="C++ 与 K8s",
                  apply_channel="https://x", location=None, remote_hint=None)
    )
    assert res.skills == ["c++", "k8s"]  # canonicalised, lowercased
    assert res.remote_policy == "onsite"
    assert (pin, pout) == (68, 34)


# --- cost -------------------------------------------------------------------
def test_glm_costs_no_cash():
    # Tokens are metered by the prepaid coding plan, not billed per call.
    assert rebuild.cost_cny(5_000_000, 500_000, "glm") == 0.0
    assert rebuild.cost_cny(5_000_000, 500_000, "deepseek") > 0.0


# --- Chinese-JD detection (drives the bake-off sample) ------------------------
def test_is_chinese_jd():
    assert rebuild.is_chinese_jd("熟悉 Linux 平台 C++ 开发，掌握 STL、多线程，"
                                 "了解 ROS 与机器人运动控制，有 CUDA 经验者优先考虑。")
    assert not rebuild.is_chinese_jd("Senior Software Engineer, distributed systems")
    assert not rebuild.is_chinese_jd("")
    # A stray Chinese company name in an English JD is not a Chinese JD.
    assert not rebuild.is_chinese_jd("Backend Engineer at 宇树 - build APIs in Go and Rust.")


# --- provenance + no cross-backend churn -------------------------------------
class _FakeGLM:
    name = "glm"

    def __init__(self, tokens=(100, 20)):
        self._tok = tokens

    def extract_with_usage(self, rec):
        return (
            ExtractionResult(skills=["ros2"], remote_policy="onsite",
                             salary_min=None, salary_max=None, salary_currency=None),
            self._tok[0], self._tok[1],
        )

    def classify_role_family_with_usage(self, rec):
        return "engineering", self._tok[0], self._tok[1]


class _AlwaysRateLimited:
    name = "glm"

    def extract_with_usage(self, rec):
        raise RateLimited("HTTP 429")

    def classify_role_family_with_usage(self, rec):
        raise RateLimited("HTTP 429")


@pytest.fixture()
def mixed_jobs():
    """3 heuristic rows, 2 already done by deepseek, 1 already done by glm."""
    init_db()
    now = dt.datetime.now(UTC)
    sources = ["heuristic"] * 3 + ["deepseek"] * 2 + ["glm"]
    with session_scope() as s:
        for t in (Job, Company):
            for row in s.execute(select(t)).scalars():
                s.delete(row)
        s.flush()
        s.add(Company(id="acme", name="Acme", ats_vendor="greenhouse", ats_tenant="acme",
                      careers_url="x", last_crawled_at=now))
        for i, src in enumerate(sources):
            s.add(Job(
                id=f"acme:{i}", company_id="acme", title=f"Role {i}",
                description_raw="rust k8s", skills=["rust"], remote_policy="remote",
                first_seen_at=now, verified_at=now, source="ats_public_api",
                apply_channel="https://x", content_hash=f"h{i}", ghost_score=0.0,
                extraction_source=src,
            ))
    return now


def _sources() -> dict[str, str]:
    with session_scope() as s:
        return {j.id: j.extraction_source for j in s.execute(select(Job)).scalars()}


def test_glm_rebuild_stamps_glm_and_skips_other_llm_rows(monkeypatch, mixed_jobs):
    monkeypatch.setattr(rebuild, "_make_extractor", lambda b, m=None: _FakeGLM())
    stats = rebuild.rebuild_extraction(batch_size=10, workers=1, backend="glm")

    assert stats.total_target == 3  # only the heuristic rows
    assert stats.updated == 3
    got = _sources()
    assert [got[f"acme:{i}"] for i in range(3)] == ["glm"] * 3
    # DeepSeek's and the pre-existing GLM rows are untouched — no cross-backend churn.
    assert got["acme:3"] == got["acme:4"] == "deepseek"
    assert got["acme:5"] == "glm"


def test_glm_rebuild_costs_nothing(monkeypatch, mixed_jobs):
    monkeypatch.setattr(rebuild, "_make_extractor", lambda b, m=None: _FakeGLM())
    stats = rebuild.rebuild_extraction(batch_size=10, workers=1, backend="glm")
    assert stats.prompt_tokens > 0  # tokens ARE counted...
    assert stats.cost == 0.0        # ...they just cost no cash


def test_rebuild_halts_after_consecutive_429s(monkeypatch, mixed_jobs):
    monkeypatch.setattr(rebuild, "_make_extractor", lambda b, m=None: _AlwaysRateLimited())
    monkeypatch.setattr(rebuild, "_429_BACKOFF_SECONDS", ())  # no real sleeping in tests
    monkeypatch.setattr(rebuild, "MAX_CONSECUTIVE_429", 2)
    stats = rebuild.rebuild_extraction(batch_size=10, workers=1, backend="glm")

    assert stats.halted and "429" in (stats.halt_reason or "")
    assert stats.updated == 0
    assert stats.rate_limited >= 2
    # Nothing was written, so a re-run resumes on exactly the same rows.
    assert list(_sources().values()).count("heuristic") == 3


def test_role_family_backfill_via_glm(monkeypatch, mixed_jobs):
    monkeypatch.setattr(rebuild, "_make_extractor", lambda b, m=None: _FakeGLM())
    stats = rebuild.rebuild_role_family(batch_size=10, workers=1, backend="glm")
    assert stats.updated == 6 and stats.cost == 0.0
    with session_scope() as s:
        assert all(j.role_family == "engineering"
                   for j in s.execute(select(Job)).scalars())


def test_rollback_restores_every_llm_source(monkeypatch, mixed_jobs):
    monkeypatch.setattr(rebuild, "_make_extractor", lambda b, m=None: _FakeGLM())
    rebuild.rebuild_extraction(batch_size=10, workers=1, backend="glm")
    restored = rebuild.rollback_extraction()
    assert restored == 6  # 3 fresh glm + 2 deepseek + 1 pre-existing glm
    assert set(_sources().values()) == {"heuristic"}
