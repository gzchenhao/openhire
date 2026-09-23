"""NIO 蔚来 careers mirror: the employer's own site, read as a first-party source.

GET https://www.nio.cn/careers/jobs

The page is server-rendered Next.js. The whole 社招 roster ships inside
``<script id="__NEXT_DATA__">`` at ``props.pageProps.jobsLists.jobs`` (1,784 rows on
2026-09-23, verified with a plain GET: no cookie, no token, no signature). Each row
carries ``id`` (the Feishu Hire job id), ``title``, ``open_date`` (Beijing-local, to the
second), ``commitment`` (社招 throughout), ``location`` (a city), ``org_level2/3``,
``job_function_level1/2`` and ``url`` (the job's page on ``nio.jobs.feishu.cn``).

Why a mirror and not the ATS: NIO hires through Feishu Hire, whose job-list API signs
every request with a ByteDance ``_signature``. That is access control, so it is not
crawled (reports/014). The employer's own site publishes the same roster in the clear,
which is squarely inside the crawl boundary (reports/020). ``www.nio.cn/robots.txt``
(checked 2026-09-23) disallows ``/admin``, ``/account``, ``/user``, ``/bff/api/v1`` and
``/developer`` for every agent; ``/careers`` is open.

What the mirror does NOT carry, and what happens instead:

* **No description.** ``description_raw`` is ``""``. The detail page sits behind the same
  Feishu front end, so it is not fetched, and nothing is invented in its place: the
  extractors treat an empty JD as "no skills", never as "extract from the title"
  (see ``pipeline/extract.py``).
* **No salary.** Stays NULL.
* **``url`` is ``http://``.** The Feishu host 301s to https; the apply resolver only trusts
  https, so the stored ``apply_channel`` is the canonical https form of the same URL.

One GET per refresh. The tenant is the single string ``"nio"``: there is exactly one
employer on this source by construction.

**Live status (2026-09-23): blocked for this client.** The same GET answers 200 to curl
and 567 to httpx from the same machine, minute for minute, whatever the User-Agent or
Accept header. The 567 body is a Tencent Cloud EdgeOne page: 请求已被站点的安全策略拦截,
本站点已启用安全防护服务以抵御在线攻击, with a request ID to quote to the site owner. It
tells the two clients apart below HTTP, by TLS handshake, and a trimmed cipher list does
get a 200. That is a bot-management rule the site owner configured, which is access
control in the sense of reports/020, so it is NOT worked around: no cipher tuning, no
fingerprint impersonation, no retry. `fetch` names the block in its error and the seed
roster keeps the row parked (see ``seed/candidates.py``) until the owner is asked.
"""

from __future__ import annotations

import datetime as dt
import json
import re

import httpx

from .base import ATSClient, FetchResult, JobRecord

_PAGE_URL = "https://www.nio.cn/careers/jobs"
_TENANT = "nio"

_NEXT_DATA_RE = re.compile(
    r'<script\s+id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S
)

# Beijing time: `open_date` is naive and local to the employer.
_CN_TZ = dt.timezone(dt.timedelta(hours=8))

# Tencent Cloud EdgeOne answers a blocked request with this status and a page that names
# the product. It is the site owner's security policy, so it is reported, not evaded.
_EDGEONE_BLOCK_STATUS = 567
_EDGEONE_BLOCK_ERROR = (
    "blocked by the site's security policy (Tencent EdgeOne 567): "
    "access control, not worked around"
)


class NioClient(ATSClient):
    vendor = "nio"

    def endpoint(self, tenant: str) -> str:
        return _PAGE_URL

    def careers_url(self, tenant: str) -> str:
        return _PAGE_URL

    @staticmethod
    def _has_jobs_array(payload) -> bool:
        return isinstance(NioClient._jobs(payload), list)

    @staticmethod
    def _jobs(payload):
        """`props.pageProps.jobsLists.jobs`, or None when the shape is not there."""
        try:
            return payload["props"]["pageProps"]["jobsLists"]["jobs"]
        except (KeyError, TypeError):
            return None

    @staticmethod
    def parse_next_data(page_html: str) -> dict:
        """Pull the `__NEXT_DATA__` JSON out of the server-rendered page."""
        m = _NEXT_DATA_RE.search(page_html or "")
        if not m:
            raise ValueError("no __NEXT_DATA__ on careers page")
        data = json.loads(m.group(1))
        if not isinstance(data, dict):
            raise ValueError("__NEXT_DATA__ is not a JSON object")
        return data

    # --- fetch -----------------------------------------------------------------
    async def fetch(self, client: httpx.AsyncClient, tenant: str) -> FetchResult:
        """One GET of the careers page. Valid only on HTTP 200 + a jobs array inside
        `__NEXT_DATA__`; an HTML 200 that lost the roster is rejected, not stored empty."""
        if tenant != _TENANT:
            return FetchResult(ok=False, status=0, error=f"nio tenant must be {_TENANT!r}")
        try:
            resp = await client.get(
                self.endpoint(tenant), headers={"Accept": "text/html,application/xhtml+xml"}
            )
        except httpx.HTTPError as exc:
            return FetchResult(ok=False, status=0, error=f"{type(exc).__name__}: {exc}")

        if resp.status_code == _EDGEONE_BLOCK_STATUS and "EdgeOne" in resp.text:
            return FetchResult(ok=False, status=resp.status_code, error=_EDGEONE_BLOCK_ERROR)
        if resp.status_code != 200:
            return FetchResult(ok=False, status=resp.status_code, error="non-200")

        try:
            payload = self.parse_next_data(resp.text)
        except ValueError as exc:
            return FetchResult(ok=False, status=200, error=str(exc))

        if not self._has_jobs_array(payload):
            return FetchResult(ok=False, status=200, error="no jobs array")

        try:
            records = self.parse(payload, tenant)
        except Exception as exc:  # a malformed record set should not kill the crawl
            return FetchResult(ok=False, status=200, error=f"parse error: {exc}")

        return FetchResult(ok=True, status=200, records=records)

    # --- parsing ---------------------------------------------------------------
    def parse(self, payload, tenant: str) -> list[JobRecord]:
        records: list[JobRecord] = []
        for j in self._jobs(payload) or []:
            if not isinstance(j, dict):
                continue
            ats_job_id = str(j.get("id") or "").strip()
            title = str(j.get("title") or "").strip()
            if not ats_job_id or not title:
                continue
            location = self._location(j)
            records.append(
                JobRecord(
                    ats_job_id=ats_job_id,
                    title=title,
                    # The mirror carries no JD. Empty means empty: no skills, no salary,
                    # and nothing derived from the title in their place.
                    description_raw="",
                    apply_channel=self.resolve_apply(tenant, ats_job_id, j.get("url")),
                    location=location,
                    remote_hint=self._remote_hint(j, location),
                    salary_min=None,
                    salary_max=None,
                    salary_currency=None,
                    salary_period="monthly",  # domestic convention; no pay is published
                    posted_at=self._date(j.get("open_date")),
                    updated_at=None,
                )
            )
        return records

    @staticmethod
    def _location(j: dict) -> str | None:
        loc = str(j.get("location") or "").strip()
        return loc or None

    @staticmethod
    def _remote_hint(j: dict, location: str | None) -> str:
        """No workplace-type field on the mirror; only an explicit 远程 marker is trusted."""
        blob = f"{j.get('title') or ''} {location or ''}"
        if "远程" in blob or "remote" in blob.lower():
            return "remote"
        return "unknown"

    @staticmethod
    def _date(raw) -> dt.datetime | None:
        """The employer's `open_date`, or None. Never the crawl time."""
        if not raw or not isinstance(raw, str):
            return None
        try:
            parsed = dt.datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.year <= 1:
            return None
        if parsed.tzinfo is None:  # naive timestamps are Beijing-local
            parsed = parsed.replace(tzinfo=_CN_TZ)
        return parsed.astimezone(dt.timezone.utc)
