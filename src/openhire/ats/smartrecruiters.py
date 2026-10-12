"""SmartRecruiters public Posting API (no key).

GET https://api.smartrecruiters.com/v1/companies/{company}/postings?limit=100&offset=N
GET https://api.smartrecruiters.com/v1/companies/{company}/postings/{postingId}

The list carries name, releasedDate and location but no description; the per-posting
detail carries jobAd.sections (HTML) and applyUrl. The careers site is
jobs.smartrecruiters.com/{company}. Customers whose plan does not expose the public feed
answer 404 or an empty list; either is reported as "not a tenant we can read", never as a
fact about the employer.

Detail calls run under a small semaphore so a large tenant (thousands of postings) stays a
polite, bounded read. Written from the vendor's documentation (reports/075); the cloud
session cannot reach api.smartrecruiters.com, so the first live read ran on the
maintainer's machine through the local task queue.
"""

from __future__ import annotations

import asyncio

import httpx

from .base import ATSClient, FetchResult, JobRecord, _iso_to_dt, html_to_text

_PAGE = 100
_MAX_PAGES = 50          # 5,000 postings; nobody in our sectors is bigger
_DETAIL_CONCURRENCY = 6


class SmartRecruitersClient(ATSClient):
    vendor = "smartrecruiters"

    def endpoint(self, tenant: str, offset: int = 0) -> str:
        return f"https://api.smartrecruiters.com/v1/companies/{tenant}/postings?limit={_PAGE}&offset={offset}"

    def detail_endpoint(self, tenant: str, posting_id: str) -> str:
        return f"https://api.smartrecruiters.com/v1/companies/{tenant}/postings/{posting_id}"

    def careers_url(self, tenant: str) -> str:
        return f"https://jobs.smartrecruiters.com/{tenant}"

    @staticmethod
    def _has_jobs_array(payload) -> bool:
        return isinstance(payload, dict) and isinstance(payload.get("content"), list)

    async def fetch(self, client: httpx.AsyncClient, tenant: str) -> FetchResult:
        """Every list page, then one bounded detail call per posting for the description."""
        rows: list[dict] = []
        for pageno in range(_MAX_PAGES):
            try:
                resp = await client.get(self.endpoint(tenant, pageno * _PAGE))
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
                return FetchResult(ok=False, status=200, error="non-json body")
            if not self._has_jobs_array(payload):
                if rows:
                    break
                return FetchResult(ok=False, status=200, error="no jobs array")
            batch = payload["content"]
            rows.extend(r for r in batch if isinstance(r, dict))
            total = payload.get("totalFound")
            if len(batch) < _PAGE or (isinstance(total, int) and len(rows) >= total):
                break

        details = await self._fetch_details(client, tenant, rows)
        for r in rows:
            d = details.get(str(r.get("id")))
            if isinstance(d, dict):
                r["jobAd"] = d.get("jobAd")
                r["applyUrl"] = d.get("applyUrl")
                r["postingUrl"] = d.get("postingUrl")
        try:
            records = self.parse({"content": rows}, tenant)
        except Exception as exc:  # a malformed record set should not kill the crawl
            return FetchResult(ok=False, status=200, error=f"parse error: {exc}")
        return FetchResult(ok=True, status=200, records=records)

    async def _fetch_details(self, client: httpx.AsyncClient, tenant: str, rows: list[dict]) -> dict[str, dict]:
        sem = asyncio.Semaphore(_DETAIL_CONCURRENCY)
        out: dict[str, dict] = {}

        async def one(pid: str) -> None:
            async with sem:
                try:
                    resp = await client.get(self.detail_endpoint(tenant, pid))
                except httpx.HTTPError:
                    return
                if resp.status_code != 200:
                    return
                try:
                    out[pid] = resp.json()
                except ValueError:
                    return

        await asyncio.gather(*(one(str(r["id"])) for r in rows if r.get("id")))
        return out

    def parse(self, payload, tenant: str) -> list[JobRecord]:
        records: list[JobRecord] = []
        for p in payload["content"]:
            pid = str(p.get("id") or "").strip()
            if not pid:
                continue
            loc = p.get("location") if isinstance(p.get("location"), dict) else {}
            sections = (p.get("jobAd") or {}).get("sections") or {}
            desc_html = "\n\n".join(
                s.get("text") for s in sections.values() if isinstance(s, dict) and isinstance(s.get("text"), str)
            )
            vendor_url = p.get("applyUrl") or p.get("postingUrl")
            records.append(
                JobRecord(
                    ats_job_id=pid,
                    title=(p.get("name") or "").strip(),
                    description_raw=html_to_text(desc_html),
                    apply_channel=self.resolve_apply(tenant, pid, vendor_url),
                    location=self._location(loc),
                    remote_hint=self._remote_hint(loc),
                    posted_at=_iso_to_dt(p.get("releasedDate")),
                    # The public feed carries no last-touched field.
                    updated_at=None,
                )
            )
        return records

    @staticmethod
    def _location(loc: dict) -> str | None:
        full = loc.get("fullLocation")
        if isinstance(full, str) and full.strip():
            return full.strip()
        parts = [loc.get("city"), loc.get("region"), loc.get("country")]
        text = ", ".join(str(p).strip() for p in parts if p and str(p).strip())
        return text or None

    @staticmethod
    def _remote_hint(loc: dict) -> str:
        if loc.get("remote") is True:
            return "remote"
        if loc.get("hybrid") is True:
            return "hybrid"
        return "unknown"
