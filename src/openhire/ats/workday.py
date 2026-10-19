"""Workday career sites: the public JSON the careers page itself loads (no key).

POST https://{account}.{wdN}.myworkdayjobs.com/wday/cxs/{account}/{site}/jobs
     {"appliedFacets": {}, "limit": 20, "offset": N, "searchText": ""}
GET  https://{account}.{wdN}.myworkdayjobs.com/wday/cxs/{account}/{site}{externalPath}

The list answers `total` and `jobPostings` (title, externalPath, locationsText, a relative
`postedOn` such as "Posted 3 Days Ago", bulletFields with the req id), twenty per page.
The per-posting detail answers `jobPostingInfo` with the description HTML, the location,
the req id, the external URL and `startDate`, the posting date as a plain day: that is the
date this index stores, so a Workday row is `ats_reported` like a Greenhouse one.

Why this is a public endpoint and not an access control (reports/020): the browser gets
exactly these responses with no login, no captcha and no request signature; the only
state is a session cookie the site hands out on the first page view, which the client
below collects by loading the careers page once before asking for the list. Workday
career sites are indexed by search engines; reading them at a weekly cadence with a
named User-Agent is what every job search engine does.

Written from the endpoint's well-known shape (reports/081): the cloud session cannot reach
myworkdayjobs.com, so the first live reads run on the maintainer's machine through the
local task queue before any Workday employer enters the seed list. A payload whose shape
differs is reported as "unexpected payload", never as a fact about the employer.

The tenant string this index keys on is "<account>.<wdN>/<site>" (ats/boards.py): one
account can publish several sites and the cluster is part of the host.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import re

import httpx

from .base import ATSClient, FetchResult, JobRecord, html_to_text, workday_host
from .workable import _date_to_dt

_PAGE = 20              # Workday caps the list at 20 per request
_MAX_PAGES = 150        # 3,000 postings; large enough for any employer in our sectors
_DETAIL_CONCURRENCY = 6
_RELATIVE = re.compile(r"posted\s+(today|yesterday|(\d+)\+?\s+days?\s+ago)", re.I)


def _parts(tenant: str) -> tuple[str, str, str]:
    """(host, account, site) for a tenant string such as nvidia.wd5/NVIDIAExternalCareerSite."""
    head, _, site = tenant.partition("/")
    account = head.split(".", 1)[0]
    return workday_host(tenant), account, site


def _relative_to_dt(text: str | None, today: dt.date | None = None) -> dt.datetime | None:
    """"Posted 3 Days Ago" -> that day at 00:00 UTC; "Posted 30+ Days Ago" -> None, because
    the list only says "at least a month" and a date this index stores must be a date."""
    if not text:
        return None
    m = _RELATIVE.search(text)
    if not m:
        return None
    today = today or dt.datetime.now(dt.timezone.utc).date()
    word = m.group(1).lower()
    if word == "today":
        days = 0
    elif word == "yesterday":
        days = 1
    else:
        if "+" in m.group(0):
            return None
        days = int(m.group(2))
    d = today - dt.timedelta(days=days)
    return dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc)


class WorkdayClient(ATSClient):
    vendor = "workday"

    def endpoint(self, tenant: str) -> str:
        host, account, site = _parts(tenant)
        return f"https://{host}/wday/cxs/{account}/{site}/jobs"

    def detail_endpoint(self, tenant: str, external_path: str) -> str:
        host, account, site = _parts(tenant)
        return f"https://{host}/wday/cxs/{account}/{site}{external_path}"

    def careers_url(self, tenant: str) -> str:
        host, _account, site = _parts(tenant)
        return f"https://{host}/{site}"

    @staticmethod
    def _has_jobs_array(payload) -> bool:
        return isinstance(payload, dict) and isinstance(payload.get("jobPostings"), list)

    async def fetch(self, client: httpx.AsyncClient, tenant: str) -> FetchResult:
        host, _account, site = _parts(tenant)
        if not site:
            return FetchResult(ok=False, status=0, error="a Workday tenant needs a site: <account>.wdN/<site>")
        # The careers page sets the session cookie the data endpoint expects; one GET,
        # failures ignored (many tenants answer the list without it).
        try:
            await client.get(f"https://{host}/{site}", headers={"Accept": "text/html"})
        except httpx.HTTPError:
            pass
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        try:
            csrf = client.cookies.get("CALYPSO_CSRF_TOKEN")
        except Exception:  # a client without a cookie jar (tests)
            csrf = None
        if csrf:
            headers["X-CALYPSO-CSRF-TOKEN"] = csrf

        rows: list[dict] = []
        total: int | None = None
        for pageno in range(_MAX_PAGES):
            body = {"appliedFacets": {}, "limit": _PAGE, "offset": pageno * _PAGE, "searchText": ""}
            try:
                resp = await client.post(self.endpoint(tenant), json=body, headers=headers)
            except httpx.HTTPError as exc:
                if rows:
                    break
                return FetchResult(ok=False, status=0, error=f"{type(exc).__name__}: {exc}")
            if resp.status_code != 200:
                if rows:
                    break
                return FetchResult(ok=False, status=resp.status_code, error="non-200")
            try:
                payload = resp.json()
            except ValueError:
                if rows:
                    break
                return FetchResult(ok=False, status=resp.status_code, error="invalid JSON")
            if not self._has_jobs_array(payload):
                if rows:
                    break
                return FetchResult(ok=False, status=resp.status_code, error="unexpected payload")
            batch = [j for j in payload["jobPostings"] if isinstance(j, dict)]
            rows.extend(batch)
            # Workday answers the real total on the first page only and 0 on every page
            # after it (seen live 2026-10-15: NVIDIA, Intel and Manulife all stopped at 40),
            # so the first positive total is the one to trust.
            reported = payload.get("total")
            if total is None and isinstance(reported, int) and reported > 0:
                total = reported
            if len(batch) < _PAGE or (total is not None and len(rows) >= total):
                break

        details = await self._fetch_details(client, tenant, rows, headers)
        records = self.parse({"jobPostings": rows, "details": details}, tenant)
        return FetchResult(ok=True, status=200, records=records)

    async def _fetch_details(self, client: httpx.AsyncClient, tenant: str, rows: list[dict], headers: dict) -> dict[str, dict]:
        sem = asyncio.Semaphore(_DETAIL_CONCURRENCY)
        out: dict[str, dict] = {}

        async def one(path: str) -> None:
            async with sem:
                try:
                    resp = await client.get(self.detail_endpoint(tenant, path), headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        info = data.get("jobPostingInfo") if isinstance(data, dict) else None
                        if isinstance(info, dict):
                            out[path] = info
                except (httpx.HTTPError, ValueError):
                    pass  # one missing description must not fail the whole board

        paths = [r.get("externalPath") for r in rows if isinstance(r.get("externalPath"), str)]
        await asyncio.gather(*(one(p) for p in paths))
        return out

    def parse(self, payload, tenant: str) -> list[JobRecord]:
        host, _account, site = _parts(tenant)
        details = payload.get("details") or {}
        records: list[JobRecord] = []
        for j in payload.get("jobPostings") or []:
            path = j.get("externalPath")
            if not isinstance(path, str) or not path:
                continue
            info = details.get(path) or {}
            bullets = [b for b in (j.get("bulletFields") or []) if isinstance(b, str) and b.strip()]
            ats_job_id = str(info.get("jobReqId") or (bullets[0] if bullets else "") or path.rsplit("_", 1)[-1]).strip()
            if not ats_job_id:
                continue
            locations = [info.get("location")] + list(info.get("additionalLocations") or [])
            locations = [str(x).strip() for x in locations if x and str(x).strip()]
            location = "; ".join(dict.fromkeys(locations)) or (j.get("locationsText") or None)
            vendor_url = info.get("externalUrl") if isinstance(info.get("externalUrl"), str) else None
            page_url = f"https://{host}/{site}{path}"
            records.append(
                JobRecord(
                    ats_job_id=ats_job_id,
                    title=(info.get("title") or j.get("title") or "").strip(),
                    description_raw=html_to_text(info.get("jobDescription") or ""),
                    apply_channel=self.resolve_apply(tenant, ats_job_id, vendor_url or page_url),
                    location=location,
                    remote_hint=self._remote_hint(info, location),
                    posted_at=_date_to_dt(info.get("startDate")) or _relative_to_dt(j.get("postedOn") or info.get("postedOn")),
                    updated_at=None,  # Workday reports no last-touched date on the public site
                )
            )
        return records

    @staticmethod
    def _remote_hint(info: dict, location: str | None) -> str:
        rt = str(info.get("remoteType") or "").strip().lower()
        if rt in ("remote", "hybrid", "onsite"):
            return rt
        if "remote" in (location or "").lower():
            return "remote"
        return "unknown"
