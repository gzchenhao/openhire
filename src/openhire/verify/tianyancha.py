"""Tianyancha (天眼查) company register lookup with the USER'S OWN key.

The registry record behind a Chinese company (成立日期、经营状态、注册资本、参保人数、法定
代表人) sits behind captchas on the government site and behind a paid API at 天眼查. The
seeker who wants it pays 天眼查 for it, with a key from open.tianyancha.com, and sets it
on their own machine:

    TIANYANCHA_API_KEY=...   (the stdio server runs on the seeker's machine; the key
                              never reaches us, and neither does what they look up)

Without the key the `registry_record` check comes back `pending_user` with the ways to
get it, and the tool costs nobody anything. With it, one call per check, charged by
天眼查 to the seeker's own account. Nothing fetched here is cached in the index or in the
public snapshot: it is 天眼查's data, shown once to the person who paid for it.

Endpoint shape (企业基本信息，普通版) as documented on the open platform: GET
`https://open.api.tianyancha.com/services/open/ic/baseinfo/normal?keyword=<name>` with
header `Authorization: <key>`; envelope `{"error_code": 0, "reason": "ok", "result": {...}}`.
This module has not yet been exercised against a live key (reports/065); any surprise in
the envelope is reported as `unavailable` with the raw reason, never as a fact about the
company. Error codes and the date convention follow 天眼查's own command-line client
(npm tyc-cli, read 2026-10-21): 300000 is "no result", not a failure; 300006 is an empty
balance; dates are Beijing midnight in milliseconds. The base-info endpoint is an exact
lookup, so a brand name (宇树) often finds nothing where the registered name or the
unified social credit code does.
"""

from __future__ import annotations

import datetime as dt
import os

import httpx

from .. import config

ENV_KEY = "TIANYANCHA_API_KEY"
_BASEINFO = "https://open.api.tianyancha.com/services/open/ic/baseinfo/normal"


def api_key() -> str | None:
    return os.environ.get(ENV_KEY) or None


_BEIJING = dt.timezone(dt.timedelta(hours=8))

# error_code → what it means; the ones that say something about the key or the account
# rather than about the request get reason "key", so the seeker knows what to fix.
_ERROR_MEANING = {
    300001: "请求失败", 300002: "账号失效", 300003: "账号过期", 300004: "访问频率过快",
    300005: "无权限访问此接口", 300006: "余额不足", 300007: "剩余次数不足", 300008: "缺少必要参数",
    300009: "账号信息有误", 300010: "接口地址不存在",
    300011: "此 IP 无权访问此接口（天眼查不支持中国大陆、港澳台以外的 IP）", 300012: "报告生成中",
}
_KEY_ERRORS = {300002, 300003, 300005, 300006, 300007, 300009, 300011}


def _ms_to_date(ms) -> str | None:
    """天眼查 stores a date as Beijing midnight; read in UTC it lands on the day before."""
    try:
        return dt.datetime.fromtimestamp(int(ms) / 1000, tz=_BEIJING).date().isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _no_record(name: str) -> dict:
    return {"status": "not_verified", "reason": "no_record",
            "note": f"天眼查没有找到名为「{name}」的登记记录。这个接口是精确查询，用登记全称或统一社会信用代码再试一次"}


def normalise(result: dict) -> dict:
    """Keep only what a seeker needs to see, with 天眼查's own field names mapped once."""
    return {
        "name": result.get("name"),
        "credit_code": result.get("creditCode"),
        "reg_status": result.get("regStatus"),
        "established": _ms_to_date(result.get("estiblishTime")),
        "reg_capital": result.get("regCapital"),
        "insured_staff": result.get("socialStaffNum"),
        "legal_person": result.get("legalPersonName"),
        "industry": result.get("industry"),
        "reg_location": result.get("regLocation"),
        "org_type": result.get("companyOrgType"),
    }


def fetch_baseinfo(name: str, key: str | None = None) -> dict:
    """One call. Returns a check dict: verified (with `record`), not_verified (no match) or
    unavailable (no key, HTTP failure, non-zero error_code)."""
    key = key or api_key()
    if not key:
        return {"status": "pending_user", "note": f"没有 {ENV_KEY}，这一项要用你自己的天眼查 key"}
    try:
        r = httpx.get(_BASEINFO, params={"keyword": name}, headers={"Authorization": key, "User-Agent": config.USER_AGENT},
                      timeout=config.HTTP_TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        return {"status": "unavailable", "reason": "network", "note": f"天眼查接口请求失败：{type(exc).__name__}"}
    if r.status_code != 200:
        return {"status": "unavailable", "reason": "http_status", "note": f"天眼查接口返回 HTTP {r.status_code}"}
    try:
        body = r.json()
    except ValueError:
        return {"status": "unavailable", "reason": "http_status", "note": "天眼查接口返回的不是 JSON"}
    try:
        code = int(body.get("error_code"))
    except (TypeError, ValueError):
        code = None
    if code == 300000:
        return _no_record(name)
    if code != 0:
        meaning = _ERROR_MEANING.get(code, "未知错误")
        return {"status": "unavailable",
                "reason": "key" if code in _KEY_ERRORS else ("rate_limited" if code == 300004 else "source_error"),
                "note": f"天眼查返回 error_code={body.get('error_code')}（{meaning}）：{body.get('reason') or ''}".rstrip("：")}
    result = body.get("result") or {}
    if not result.get("name"):
        return _no_record(name)
    rec = normalise(result)
    note = f"登记在册：{rec['reg_status'] or '状态未知'}，成立 {rec['established'] or '未知'}"
    if rec.get("insured_staff") is not None:
        note += f"，参保人数 {rec['insured_staff']}"
    return {"status": "verified", "record": rec, "note": note, "source": "天眼查 OpenAPI（你自己的 key，T+1）"}
