"""GLM multi-key rotation — quota exhaustion hot-swaps keys, cash never leaks.

Offline: HTTP is stubbed. What is locked down:
  * a spent key (HTTP 429 / provider code 1310) or an invalid key (HTTP 401) rotates
    to the next configured key and retries the SAME request;
  * a plain 429 (transient rate limit) raises RateLimited without burning a backup key;
  * when every key is dead the extractor raises RateLimited, landing the resumable
    rebuild on its normal breakpoint (never silently degrading mid-run);
  * ZHIPU_API_KEY stays the on/off switch — backups alone do not enable GLM;
  * the single-string constructor keeps working (every pre-multikey call site).
"""

from __future__ import annotations

import pytest

from openhire import config
from openhire.pipeline.extract import GLMExtractor, RateLimited, make_glm_extractor


class FakeResp:
    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self._body = body

    def json(self) -> dict:
        return self._body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeClient:
    """Serves a scripted queue of responses per API key (read live off the extractor)."""

    def __init__(self, ext: GLMExtractor, script: dict[str, list[FakeResp]]):
        self._ext = ext
        self._script = script
        self.calls: list[str] = []

    def post(self, url, json=None):
        key = self._ext._api_key
        self.calls.append(key)
        queue = self._script.get(key, [])
        if not queue:
            raise AssertionError(f"unscripted call with key {key!r}")
        return queue.pop(0)


OK_BODY = {
    "choices": [{"message": {"content": '{"role_family": "engineering"}'}}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
}
QUOTA_GONE = FakeResp(429, {"error": {"code": "1310", "message": "quota exhausted"}})
QUOTA_GONE_FLAT = FakeResp(429, {"code": "1310", "message": "quota exhausted"})
RATE_LIMIT = FakeResp(429, {"error": {"code": "1302", "message": "too many requests"}})
BAD_KEY = FakeResp(401, {"error": {"code": "1002", "message": "invalid api key"}})


def _wire(ext: GLMExtractor, script: dict[str, list[FakeResp]], monkeypatch) -> FakeClient:
    fake = FakeClient(ext, script)
    monkeypatch.setattr(GLMExtractor, "_http", lambda self: fake)
    return fake


def _ext(keys) -> GLMExtractor:
    return GLMExtractor(keys, "https://example.invalid/api/coding/paas/v4", "glm-5.3-flash")


# --- rotation behaviour --------------------------------------------------------
def test_spent_key_rotates_and_retries_same_request(monkeypatch):
    ext = _ext(["key-1", "key-2"])
    fake = _wire(ext, {"key-1": [QUOTA_GONE], "key-2": [FakeResp(200, OK_BODY)]}, monkeypatch)
    body = ext._call({"model": "glm-5.3-flash"})
    assert body == OK_BODY
    assert fake.calls == ["key-1", "key-2"]
    assert ext._key_idx == 1  # stays on the working key for subsequent calls


def test_flat_error_shape_also_counts_as_spent(monkeypatch):
    ext = _ext(["key-1", "key-2"])
    _wire(ext, {"key-1": [QUOTA_GONE_FLAT], "key-2": [FakeResp(200, OK_BODY)]}, monkeypatch)
    assert ext._call({}) == OK_BODY


def test_invalid_key_is_skipped_like_a_spent_one(monkeypatch):
    ext = _ext(["key-1", "key-2"])
    _wire(ext, {"key-1": [BAD_KEY], "key-2": [FakeResp(200, OK_BODY)]}, monkeypatch)
    assert ext._call({}) == OK_BODY


def test_transient_rate_limit_backs_off_without_burning_a_backup(monkeypatch):
    ext = _ext(["key-1", "key-2"])
    fake = _wire(ext, {"key-1": [RATE_LIMIT]}, monkeypatch)
    with pytest.raises(RateLimited):
        ext._call({})
    assert fake.calls == ["key-1"]
    assert ext._key_idx == 0  # the backup key was NOT consumed by a transient 429


def test_all_keys_dead_raises_rate_limited(monkeypatch):
    ext = _ext(["key-1", "key-2"])
    _wire(ext, {"key-1": [QUOTA_GONE], "key-2": [QUOTA_GONE]}, monkeypatch)
    with pytest.raises(RateLimited, match="exhausted or invalid"):
        ext._call({})


def test_single_string_key_still_constructs():
    ext = _ext("dummy-key")
    assert ext._keys == ["dummy-key"]
    assert ext._api_key == "dummy-key"


def test_empty_key_list_is_refused():
    with pytest.raises(RuntimeError):
        _ext([])


# --- config plumbing -----------------------------------------------------------
def _clear_numbered_slots(monkeypatch):
    """Isolate from whatever real backup keys live in the developer's environment."""
    for i in range(2, 10):
        monkeypatch.delenv(f"ZHIPU_API_KEY_{i}", raising=False)


def test_config_collects_numbered_keys_in_order(monkeypatch):
    _clear_numbered_slots(monkeypatch)
    monkeypatch.setattr(config, "ZHIPU_API_KEY", "primary")
    monkeypatch.setenv("ZHIPU_API_KEY_2", "second")
    monkeypatch.setenv("ZHIPU_API_KEY_3", "   ")  # unfilled template slot: skipped
    monkeypatch.setenv("ZHIPU_API_KEY_4", "fourth")
    assert config.zhipu_api_keys() == ["primary", "second", "fourth"]


def test_backup_keys_alone_do_not_enable_glm(monkeypatch):
    _clear_numbered_slots(monkeypatch)
    monkeypatch.setattr(config, "ZHIPU_API_KEY", None)
    monkeypatch.setenv("ZHIPU_API_KEY_2", "orphan-backup")
    with pytest.raises(RuntimeError):
        make_glm_extractor()


def test_make_glm_extractor_passes_every_key(monkeypatch):
    _clear_numbered_slots(monkeypatch)
    monkeypatch.setattr(config, "ZHIPU_API_KEY", "primary")
    monkeypatch.setenv("ZHIPU_API_KEY_2", "second")
    ext = make_glm_extractor()
    assert ext._keys == ["primary", "second"]
