"""Greenhouse public board API.

GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true
"""

from __future__ import annotations

from .base import ATSClient, JobRecord, _iso_to_dt, html_to_text


class GreenhouseClient(ATSClient):
    vendor = "greenhouse"

    def endpoint(self, tenant: str) -> str:
        return f"https://boards-api.greenhouse.io/v1/boards/{tenant}/jobs?content=true"

    def careers_url(self, tenant: str) -> str:
        return f"https://job-boards.greenhouse.io/{tenant}"

    @staticmethod
    def _has_jobs_array(payload) -> bool:
        return isinstance(payload, dict) and isinstance(payload.get("jobs"), list)

    def parse(self, payload, tenant: str) -> list[JobRecord]:
        records: list[JobRecord] = []
        for j in payload["jobs"]:
            loc = (j.get("location") or {}).get("name")
            ats_job_id = str(j["id"])
            records.append(
                JobRecord(
                    ats_job_id=ats_job_id,
                    title=j.get("title", "").strip(),
                    description_raw=html_to_text(j.get("content")),
                    apply_channel=self.resolve_apply(tenant, ats_job_id, j.get("absolute_url")),
                    location=loc,
                    remote_hint=self._remote_hint(j, loc),
                    posted_at=_iso_to_dt(j.get("first_published")),
                    updated_at=_iso_to_dt(j.get("updated_at")),
                )
            )
        return records

    @staticmethod
    def _remote_hint(j, loc: str | None) -> str:
        # Greenhouse exposes a "Location Type" custom field in `metadata`.
        for m in j.get("metadata") or []:
            if str(m.get("name", "")).lower() == "location type":
                val = str(m.get("value", "")).lower()
                if "remote" in val:
                    return "remote"
                if "hybrid" in val:
                    return "hybrid"
                if val in ("on-site", "onsite", "in office", "in-office"):
                    return "onsite"
        if loc and "remote" in loc.lower():
            return "remote"
        return "unknown"
