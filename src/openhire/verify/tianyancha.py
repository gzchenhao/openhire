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
company.
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


def _ms_to_date(ms) -> str | None:
    try:
        return dt.datetime.fromtimestamp(int(ms) / 1000, tz=dt.timezone.utc).date().isoformat()
    except (TypeError, ValueError, OSError):
        return None


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
        return {"status": "unavailable", "note": f"天眼查接口请求失败：{type(exc).__name__}"}
    if r.status_code != 200:
        return {"status": "unavailable", "note": f"天眼查接口返回 HTTP {r.status_code}"}
    try:
        body = r.json()
    except ValueError:
        return {"status": "unavailable", "note": "天眼查接口返回的不是 JSON"}
    code = body.get("error_code")
    if code not in (0, "0"):
        return {"status": "unavailable", "note": f"天眼查返回 error_code={code}：{body.get('reason') or ''}".strip()}
    result = body.get("result") or {}
    if not result.get("name"):
        return {"status": "not_verified", "note": f"天眼查没有找到名为「{name}」的登记记录"}
    rec = normalise(result)
    note = f"登记在册：{rec['reg_status'] or '状态未知'}，成立 {rec['established'] or '未知'}"
    if rec.get("insured_staff") is not None:
        note += f"，参保人数 {rec['insured_staff']}"
    return {"status": "verified", "record": rec, "note": note, "source": "天眼查 OpenAPI（你自己的 key，T+1）"}
