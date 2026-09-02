"""Moka (moka.hr) recruitment-portal API — the ATS behind `app.mokahr.com/apply/<org>`.

Discovery (2026-09-02, see reports/020). Every employer portal is addressed by an org
slug plus a numeric site id, so this client's `tenant` is the pair, `"<org>/<siteId>"`,
which is exactly the path in the public URL: `app.mokahr.com/apply/yushi/3774`.

Three requests make a crawl:

1. GET  ``/apply/<org>/<siteId>`` — the server-rendered portal page. Its hidden
   ``#init-data`` input holds a plaintext JSON blob with the org record and ``aesIv``.
2. POST ``/api/outer/ats-apply/website/jobs``  {limit, offset, siteId, orgId, site} —
   the paged 社招 roster. Carries no description and no salary.
3. POST ``/api/outer/ats-apply/website/job``   {orgId, jobId, siteId} — one call per job
   for ``jobDescription`` (and ``minSalary``/``maxSalary`` where the org publishes pay).

**On the AES envelope.** Both POST responses come back as ``{"data": <base64>,
"necromancer": <key>}``, AES-128-CBC. This is not an access control and there is nothing
to break: the endpoint is public and unauthenticated, the key ships *inside the very
response it encrypts*, and the IV sits in plaintext in the page HTML. It is a transport
encoding — base64 with extra steps — not the same family as the ByteDance `_signature`
that made Feishu Hire uncrawlable (reports/014). No signature is computed, no captcha is
solved, no login is bypassed, no rate limit is evaded. See `_aes.py`.

Politeness: a module-level semaphore caps concurrent Moka orgs at 2 (stricter than the
global cap), list pages and per-job detail calls are serial within an org, and detail
calls are additionally spaced by `_DETAIL_DELAY_SECONDS`. The 30-minute per-tenant floor
is enforced upstream by `due_companies()`.
"""

from __future__ import annotations

import asyncio
import base64
import datetime as dt
import html
import json
import re

import httpx

from ._aes import decrypt_cbc
from .base import ATSClient, FetchResult, JobRecord, html_to_text

_HOST = "https://app.mokahr.com"

# Domestic ATS politeness: at most 2 Moka orgs in flight at once.
_MOKA_SEMAPHORE = asyncio.Semaphore(2)

_PAGE_SIZE = 100
_MAX_PAGES = 20            # 2,000 postings per org — far above any observed roster
_MAX_DETAILS = 400         # ceiling on per-job calls, so one huge org cannot run away
_DETAIL_DELAY_SECONDS = 0.2

_INIT_DATA_RE = re.compile(r'id="init-data"[^>]*value="(.*?)"', re.S)

# Beijing time: the portal's naive timestamps are local to the tenant.
_CN_TZ = dt.timezone(dt.timedelta(hours=8))

# Moka stores pay as bare numbers with no usable unit flag: the same employer files
# "35-57" and "35000-60000" for comparable bands (robosense, 2026-09-02), i.e. the small
# form is the 千元/月 shorthand every Chinese posting uses. Anything under this bound is
# read as thousands of yuan; anything at or above it is already yuan. Both are monthly —
# annualising (x12? x13? x16?) would be fabrication, so we never do it.
_SALARY_KILO_BOUND = 1000

# ...except that the shorthand only holds for full-time roles. Internships and part-time
# postings quote a **day** rate in the same bare field: freetech's 实习生 rows read 150-250,
# which is 150-250 元/天, not 150K-250K 元/月 (2026-09-02). There is no daily `salary_period`
# to put that in, and converting it to a month (x21.75 working days?) would be inventing a
# number the employer never published — so pay on these postings is dropped.
_NON_MONTHLY_COMMITMENTS = frozenset({"实习", "兼职"})


class MokaClient(ATSClient):
    vendor = "moka"

    @staticmethod
    def _split(tenant: str) -> tuple[str, str]:
        """`"yushi/3774"` -> `("yushi", "3774")`."""
        org, _, site = tenant.partition("/")
        if not org or not site:
            raise ValueError(f"moka tenant must be '<org>/<siteId>', got {tenant!r}")
        return org, site

    def endpoint(self, tenant: str) -> str:
        return f"{_HOST}/api/outer/ats-apply/website/jobs"

    def careers_url(self, tenant: str) -> str:
        return f"{_HOST}/apply/{tenant}"

    @staticmethod
    def _has_jobs_array(payload) -> bool:
        return isinstance(payload, dict) and isinstance(payload.get("jobs"), list)

    # --- transport -------------------------------------------------------------
    @staticmethod
    def _unwrap(payload) -> dict:
        """Decode Moka's response envelope; a plain JSON body passes straight through."""
        if not isinstance(payload, dict):
            raise ValueError("response is not a JSON object")
        key = payload.get("necromancer")
        if not key:
            return payload
        iv = payload.get("__iv__")
        if not iv:
            raise ValueError("encrypted response but no IV was read from the portal page")
        body = json.loads(
            decrypt_cbc(base64.b64decode(payload["data"]), key.encode(), iv.encode())
        )
        # The decoded envelope is {code, msg, success, data: {...}}; hand back the payload.
        inner = body.get("data")
        return inner if isinstance(inner, dict) else body

    @staticmethod
    def parse_init_data(page_html: str) -> dict:
        """Pull the plaintext `#init-data` JSON out of the server-rendered portal page."""
        m = _INIT_DATA_RE.search(page_html)
        if not m:
            raise ValueError("no init-data on portal page")
        return json.loads(html.unescape(m.group(1)))

    async def _post(
        self, client: httpx.AsyncClient, path: str, body: dict, *, iv: str, referer: str
    ) -> dict:
        resp = await client.post(
            f"{_HOST}{path}",
            json=body,
            headers={"Referer": referer, "Content-Type": "application/json"},
        )
        if resp.status_code != 200:
            raise ValueError(f"{path} returned HTTP {resp.status_code}")
        payload = resp.json()
        if isinstance(payload, dict):
            payload = dict(payload, __iv__=iv)
        return self._unwrap(payload)

    # --- fetch -----------------------------------------------------------------
    async def fetch(self, client: httpx.AsyncClient, tenant: str) -> FetchResult:
        """Portal page -> paged roster -> one detail call per job."""
        try:
            org, site = self._split(tenant)
        except ValueError as exc:
            return FetchResult(ok=False, status=0, error=str(exc))

        referer = self.careers_url(tenant)

        async with _MOKA_SEMAPHORE:
            try:
                page = await client.get(referer)
            except httpx.HTTPError as exc:
                return FetchResult(ok=False, status=0, error=f"{type(exc).__name__}: {exc}")
            if page.status_code != 200:
                return FetchResult(ok=False, status=page.status_code, error="non-200 portal")

            try:
                init = self.parse_init_data(page.text)
            except ValueError as exc:
                return FetchResult(ok=False, status=200, error=f"portal page: {exc}")
            # A wrong or retired slug renders a "页面不存在" / "已关停" shell: init-data is
            # present but carries no org, so 200 alone is never taken as proof of a tenant.
            if not init.get("org"):
                return FetchResult(ok=False, status=200, error="portal has no org (retired?)")
            iv = init.get("aesIv")
            if not iv:
                return FetchResult(ok=False, status=200, error="portal page carries no aesIv")

            rows: list[dict] = []
            try:
                for pageno in range(_MAX_PAGES):
                    data = await self._post(
                        client,
                        "/api/outer/ats-apply/website/jobs",
                        {
                            "limit": _PAGE_SIZE,
                            "offset": pageno * _PAGE_SIZE,
                            "siteId": site,
                            "orgId": org,
                            "site": "social",
                            "needStat": True,
                        },
                        iv=iv,
                        referer=referer,
                    )
                    if not self._has_jobs_array(data):
                        if rows:
                            break
                        return FetchResult(ok=False, status=200, error="no jobs array")
                    batch = data["jobs"]
                    rows.extend(batch)
                    total = (data.get("jobStats") or {}).get("total")
                    if len(batch) < _PAGE_SIZE:
                        break
                    if isinstance(total, int) and len(rows) >= total:
                        break
            except (httpx.HTTPError, ValueError) as exc:
                if not rows:
                    return FetchResult(ok=False, status=0, error=f"job list: {exc}")

            rows = [r for r in rows if (r.get("status") or "open") == "open"]
            details = await self._fetch_details(
                client, rows, org=org, site=site, iv=iv, referer=referer
            )

        try:
            records = self.parse({"jobs": rows, "details": details}, tenant)
        except Exception as exc:  # a malformed record set should not kill the crawl
            return FetchResult(ok=False, status=200, error=f"parse error: {exc}")

        return FetchResult(ok=True, status=200, records=records)

    async def _fetch_details(self, client, rows, *, org, site, iv, referer) -> dict[str, dict]:
        """One serial, spaced call per job. A job whose detail never arrives is still
        reported — dropping it would read downstream as a delisting it did not have."""
        out: dict[str, dict] = {}
        for row in rows[:_MAX_DETAILS]:
            job_id = str(row.get("id") or "")
            if not job_id:
                continue
            for attempt in (1, 2):
                try:
                    out[job_id] = await self._post(
                        client,
                        "/api/outer/ats-apply/website/job",
                        {"orgId": org, "jobId": job_id, "siteId": site},
                        iv=iv,
                        referer=referer,
                    )
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
        for j in payload["jobs"]:
            ats_job_id = str(j.get("id") or "").strip()
            if not ats_job_id:
                continue
            merged = {**j, **(details.get(ats_job_id) or {})}
            location = self._location(merged)
            smin, smax = self._salary(merged)
            records.append(
                JobRecord(
                    ats_job_id=ats_job_id,
                    title=(merged.get("title") or "").strip(),
                    description_raw=html_to_text(merged.get("jobDescription")),
                    apply_channel=self.resolve_apply(tenant, ats_job_id, None),
                    location=location,
                    remote_hint=self._remote_hint(merged, location),
                    salary_min=smin,
                    salary_max=smax,
                    salary_currency="CNY" if smin else None,
                    salary_period="monthly",  # 元/月 — never annualised on the way in
                    posted_at=self._date(merged.get("publishedAt") or merged.get("openedAt")),
                    updated_at=self._date(merged.get("updatedAt")),
                )
            )
        return records

    @staticmethod
    def _location(j: dict) -> str | None:
        """`省·市` per site, joined across sites — mirrors what the portal renders."""
        parts: list[str] = []
        for loc in j.get("locations") or []:
            if not isinstance(loc, dict):
                continue
            bits = [loc.get("provinceName"), loc.get("cityName")]
            label = "·".join(str(b) for b in bits if b)
            if label and label not in parts:
                parts.append(label)
        return " / ".join(parts) or None

    @staticmethod
    def _remote_hint(j: dict, location: str | None) -> str:
        """Moka has no workplace-type field; only an explicit 远程 marker is trusted."""
        blob = f"{j.get('title') or ''} {location or ''}"
        if "远程" in blob or "remote" in blob.lower():
            return "remote"
        return "unknown"

    @staticmethod
    def _date(raw) -> dt.datetime | None:
        """Real ATS publish date, or None — never the crawl time (P0-2)."""
        if not raw or not isinstance(raw, str):
            return None
        try:
            parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.year <= 1:
            return None
        if parsed.tzinfo is None:  # portal timestamps are Beijing-local
            parsed = parsed.replace(tzinfo=_CN_TZ)
        return parsed.astimezone(dt.timezone.utc)

    @staticmethod
    def _salary(j: dict) -> tuple[int | None, int | None]:
        """Monthly CNY as published; see `_SALARY_KILO_BOUND`. Unreadable -> NULL."""
        if (j.get("commitment") or "").strip() in _NON_MONTHLY_COMMITMENTS:
            return None, None  # a day rate, which this schema cannot express
        try:
            lo = int(j.get("minSalary") or 0)
            hi = int(j.get("maxSalary") or 0)
        except (TypeError, ValueError):
            return None, None
        if lo <= 0 or hi <= 0 or hi < lo:
            return None, None
        if lo < _SALARY_KILO_BOUND and hi < _SALARY_KILO_BOUND:
            return lo * 1000, hi * 1000
        if lo < _SALARY_KILO_BOUND or hi < _SALARY_KILO_BOUND:
            return None, None  # mixed magnitudes — we cannot tell what the employer meant
        return lo, hi
