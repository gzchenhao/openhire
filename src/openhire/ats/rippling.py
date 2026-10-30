"""Rippling public job board (no key, one call per tenant).

GET https://ats.rippling.com/api/v2/board/{slug}/jobs?page=0&pageSize=1000

The JSON behind the tenant's own careers page at `ats.rippling.com/<slug>/jobs`:
`{items: [{id, name, url, department: {name}, locations: [{name}]}], totalItems, ...}`.
The list carries no posting date and no description, so every row is
`date_signal: not_reported_by_ats` and is aged from the day this index first saw it.

Endpoint and field names follow career-ops' Rippling provider (MIT,
https://github.com/career-ops-hq/career-ops, providers/rippling.mjs), which reads the same
public board; reports/121. A plain GET with our own User-Agent, nothing else.
"""

from __future__ import annotations

from .base import ATSClient, JobRecord

HOST = "ats.rippling.com"
PAGE_SIZE = 1000


class RipplingClient(ATSClient):
    vendor = "rippling"

    def endpoint(self, tenant: str) -> str:
        return f"https://{HOST}/api/v2/board/{tenant}/jobs?page=0&pageSize={PAGE_SIZE}"

    def careers_url(self, tenant: str) -> str:
        return f"https://{HOST}/{tenant}/jobs"

    @staticmethod
    def _has_jobs_array(payload) -> bool:
        return isinstance(payload, dict) and isinstance(payload.get("items"), list)

    def parse(self, payload, tenant: str) -> list[JobRecord]:
        records: list[JobRecord] = []
        for j in payload["items"]:
            if not isinstance(j, dict):
                continue
            ats_job_id = str(j.get("id") or "").strip()
            title = (j.get("name") or "").strip()
            if not ats_job_id or not title:
                continue
            locs = [str(loc.get("name")).strip() for loc in (j.get("locations") or [])
                    if isinstance(loc, dict) and loc.get("name")]
            location = "; ".join(dict.fromkeys(locs)) or None
            remote = "remote" if location and "remote" in location.lower() else "unknown"
            records.append(JobRecord(
                ats_job_id=ats_job_id,
                title=title,
                description_raw="",
                apply_channel=self.resolve_apply(tenant, ats_job_id, j.get("url")),
                location=location,
                remote_hint=remote,
                posted_at=None,
                updated_at=None,
            ))
        return records
