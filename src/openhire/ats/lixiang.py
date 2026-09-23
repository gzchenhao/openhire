"""Li Auto (理想汽车) first-party recruitment API, the mirror behind `lixiang.com/employ`.

Unlike the other vendors this is not a multi-tenant ATS: it is one employer's own public
job mirror, so the registry holds exactly one tenant. `tenant` names the board in the API
path: `social` (社会招聘). A `school` (校招) sibling exists at the same host and is
deliberately excluded, the same way Beisen's 校招 category is.

Verified 2026-09-23 with plain GETs, no cookie, no token, no signature:

  GET https://api-web.lixiang.com/osd-hr-recruitment-website/v1/recruit/social/job-page
      ?page=1&page_size=200
      -> {"code": 0, "data": {"page", "page_size", "total_pages", "total_count", "items": [
             {"id", "code", "title", "department_title", "location_title",
              "job_mode_name", "second_job_function_title", ...}]}}
      772 postings. page_size 50 / 100 / 200 / 500 / 1000 all honoured; 1000 returns the
      whole roster in one page. We ask for 200 (four pages) rather than the maximum so a
      refresh stays a handful of small requests.
  GET .../v1/recruit/job/detail?job_id=<id>
      -> {"code": 0, "data": {"description": <html>, "requirements": <html>, ...}}

Nothing in either response is a date. Not a posting date, not a last-touched date, and
the ids are Li Auto's own sequence, not an ATS's. So `posted_at` and `updated_at` are
None on every row and the index ages these postings from `first_seen_at`, the day we first
saw them. That is the existing fallback for an ATS that reports no date; it is not a
fabricated date, and the row says so (`date_signal`). Nothing here is inferred.

robots.txt, read 2026-09-23: `www.lixiang.com` disallows only URLs with a query string
(`/?*` and `/*?*`), so the public job page `/employ/detail/<id>.html` is allowed.
`api-web.lixiang.com` serves no robots.txt (the path answers the API's own JSON envelope).

Politeness: one employer, so everything is serial: list pages one after another, then one
detail call per posting spaced by `_DETAIL_DELAY_SECONDS`. The 30-minute per-tenant floor
is enforced upstream by `due_companies()`.

The envelope carries its own error code (`{"code": 100012, "msg": "没有接口访问权限"}` for an
unknown path). A non-zero code on the job endpoints is reported as a failed fetch and
nothing else: if this mirror ever grows a signature or a login wall, it becomes access
control and the adapter is retired rather than worked around (reports/020).
"""

from __future__ import annotations

import asyncio

import httpx

from .base import ATSClient, FetchResult, JobRecord, html_to_text

_API = "https://api-web.lixiang.com/osd-hr-recruitment-website/v1/recruit"
_SITE = "https://www.lixiang.com"

# One employer: keep its list and detail calls strictly serial.
_LIXIANG_SEMAPHORE = asyncio.Semaphore(1)

_PAGE_SIZE = 200
_MAX_PAGES = 10            # 2,000 postings; the roster was 772 on 2026-09-23
_MAX_DETAILS = 1000        # ceiling on per-job calls, above the observed roster
_DETAIL_DELAY_SECONDS = 0.2

_BOARDS = frozenset({"social"})  # `school` exists but is campus hiring: excluded


class LixiangClient(ATSClient):
    vendor = "lixiang"

    def endpoint(self, tenant: str) -> str:
        return f"{_API}/{tenant}/job-page"

    def careers_url(self, tenant: str) -> str:
        return f"{_SITE}/employ/{tenant}.html"

    @staticmethod
    def _has_jobs_array(payload) -> bool:
        return isinstance(payload, dict) and isinstance(payload.get("items"), list)

    # --- transport -------------------------------------------------------------
    @staticmethod
    def _unwrap(payload) -> dict:
        """`{"code": 0, "data": {...}}` -> the data; any other code is an error."""
        if not isinstance(payload, dict):
            raise ValueError("response is not a JSON object")
        code = payload.get("code")
        if code != 0:
            raise ValueError(f"api code {code!r}: {payload.get('msg') or 'no message'}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ValueError("api envelope carries no data object")
        return data

    async def _get(self, client: httpx.AsyncClient, path: str, params: dict) -> dict:
        resp = await client.get(f"{_API}{path}", params=params,
                                headers={"Referer": self.careers_url("social")})
        if resp.status_code != 200:
            raise ValueError(f"{path} returned HTTP {resp.status_code}")
        return self._unwrap(resp.json())

    # --- fetch -----------------------------------------------------------------
    async def fetch(self, client: httpx.AsyncClient, tenant: str) -> FetchResult:
        """Paged roster, then one detail call per posting."""
        if tenant not in _BOARDS:
            return FetchResult(ok=False, status=0,
                               error=f"lixiang tenant must be one of {sorted(_BOARDS)}, got {tenant!r}")

        async with _LIXIANG_SEMAPHORE:
            rows: list[dict] = []
            status = 0
            for pageno in range(1, _MAX_PAGES + 1):
                try:
                    data = await self._get(client, f"/{tenant}/job-page",
                                           {"page": pageno, "page_size": _PAGE_SIZE})
                except httpx.HTTPError as exc:
                    if rows:  # keep what we already have; a partial roster still beats none
                        break
                    return FetchResult(ok=False, status=0, error=f"{type(exc).__name__}: {exc}")
                except ValueError as exc:
                    if rows:
                        break
                    return FetchResult(ok=False, status=200, error=f"job list: {exc}")
                status = 200
                if not self._has_jobs_array(data):
                    if rows:
                        break
                    return FetchResult(ok=False, status=200, error="no jobs array")
                batch = data["items"]
                rows.extend(batch)
                total = data.get("total_count")
                if len(batch) < _PAGE_SIZE:
                    break
                if isinstance(total, int) and len(rows) >= total:
                    break

            details = await self._fetch_details(client, rows)

        try:
            records = self.parse({"items": rows, "details": details}, tenant)
        except Exception as exc:  # a malformed record set should not kill the crawl
            return FetchResult(ok=False, status=status, error=f"parse error: {exc}")

        return FetchResult(ok=True, status=200, records=records)

    async def _fetch_details(self, client, rows) -> dict[str, dict]:
        """One serial, spaced call per posting. A posting whose detail never arrives is
        still reported (with an empty description), because dropping it would read
        downstream as a delisting it did not have."""
        out: dict[str, dict] = {}
        for row in rows[:_MAX_DETAILS]:
            job_id = str(row.get("id") or "")
            if not job_id:
                continue
            for attempt in (1, 2):
                try:
                    out[job_id] = await self._get(client, "/job/detail", {"job_id": job_id})
                    break
                except (httpx.HTTPError, ValueError):
                    if attempt == 2:
                        break
            await asyncio.sleep(_DETAIL_DELAY_SECONDS)
        return out

    # --- parsing ---------------------------------------------------------------
    def parse(self, payload, tenant: str) -> list[JobRecord]:
        details = payload.get("details") or {}
        records: list[JobRecord] = []
        for j in payload["items"]:
            ats_job_id = str(j.get("id") or "").strip()
            if not ats_job_id:
                continue
            merged = {**j, **(details.get(ats_job_id) or {})}
            location = self._location(merged)
            records.append(
                JobRecord(
                    ats_job_id=ats_job_id,
                    title=(merged.get("title") or "").strip(),
                    description_raw=self._description(merged),
                    apply_channel=self.resolve_apply(tenant, ats_job_id, None),
                    location=location,
                    remote_hint=self._remote_hint(merged, location),
                    salary_min=None,        # the mirror publishes no pay
                    salary_max=None,
                    salary_currency=None,
                    salary_period="monthly",  # CN convention, should pay ever appear
                    posted_at=None,         # the mirror carries no date at all
                    updated_at=None,
                )
            )
        return records

    @staticmethod
    def _description(j: dict) -> str:
        """岗位职责 (description) + 任职要求 (requirements), the two halves of a Chinese JD.
        Empty when the detail call did not arrive; never padded from the title."""
        parts = []
        for key in ("description", "requirements"):
            val = j.get(key)
            if val:
                parts.append(html_to_text(str(val)))
        return "\n\n".join(p for p in parts if p).strip()

    @staticmethod
    def _location(j: dict) -> str | None:
        loc = (j.get("location_title") or "").strip()
        return loc or None

    @staticmethod
    def _remote_hint(j: dict, location: str | None) -> str:
        """No workplace-type field; only an explicit 远程 marker is trusted."""
        blob = f"{j.get('title') or ''} {location or ''} {j.get('job_mode_name') or ''}"
        if "远程" in blob or "remote" in blob.lower():
            return "remote"
        return "unknown"
