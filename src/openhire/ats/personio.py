"""Personio public job feed (no key, one call per tenant).

GET https://{tenant}.jobs.personio.de/xml?language=en

Personio documents this XML feed for employers who want their open positions on other
sites: `<workzag-jobs><position>` with `id`, `name`, `office`, `createdAt`,
`schedule`, and `<jobDescriptions>` (HTML). `createdAt` is the employer's own posting
time. Common with European robotics employers (Wandelbots, Franka Robotics; reports/121).
A plain GET with our own User-Agent.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

import httpx

from .base import ATSClient, FetchResult, JobRecord, _iso_to_dt, html_to_text


class PersonioClient(ATSClient):
    vendor = "personio"

    def endpoint(self, tenant: str) -> str:
        return f"https://{tenant}.jobs.personio.de/xml?language=en"

    def careers_url(self, tenant: str) -> str:
        return f"https://{tenant}.jobs.personio.de/"

    @staticmethod
    def _has_jobs_array(payload) -> bool:
        return isinstance(payload, ET.Element) and payload.tag == "workzag-jobs"

    async def fetch(self, client: httpx.AsyncClient, tenant: str) -> FetchResult:
        try:
            resp = await client.get(self.endpoint(tenant))
        except httpx.HTTPError as exc:
            return FetchResult(ok=False, status=0, error=f"{type(exc).__name__}: {exc}")
        if resp.status_code != 200:
            return FetchResult(ok=False, status=resp.status_code, error="non-200")
        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError:
            return FetchResult(ok=False, status=200, error="non-xml body")
        if not self._has_jobs_array(root):
            return FetchResult(ok=False, status=200, error="no jobs array")
        try:
            return FetchResult(ok=True, status=200, records=self.parse(root, tenant))
        except Exception as exc:
            return FetchResult(ok=False, status=200, error=f"parse error: {exc}")

    def parse(self, payload, tenant: str) -> list[JobRecord]:
        records: list[JobRecord] = []
        for p in payload.findall("position"):
            ats_job_id = (p.findtext("id") or "").strip()
            title = (p.findtext("name") or "").strip()
            if not ats_job_id or not title:
                continue
            offices = [o.strip() for o in [p.findtext("office") or ""] + [x.text or "" for x in p.findall("additionalOffices/office")] if o.strip()]
            location = "; ".join(dict.fromkeys(offices)) or None
            parts = []
            for d in p.findall("jobDescriptions/jobDescription"):
                name, value = (d.findtext("name") or "").strip(), (d.findtext("value") or "").strip()
                if value:
                    parts.append(f"{name}\n{value}" if name else value)
            created = _iso_to_dt((p.findtext("createdAt") or "").strip())
            remote = "remote" if location and "remote" in location.lower() else "unknown"
            records.append(JobRecord(
                ats_job_id=ats_job_id,
                title=title,
                description_raw=html_to_text("\n\n".join(parts)),
                apply_channel=self.resolve_apply(tenant, ats_job_id, None),
                location=location,
                remote_hint=remote,
                posted_at=created,
                updated_at=None,
            ))
        return records
