"""Lever public postings API.

GET https://api.lever.co/v0/postings/{site}?mode=json
"""

from __future__ import annotations

from .base import ATSClient, JobRecord, _epoch_ms_to_dt


class LeverClient(ATSClient):
    vendor = "lever"

    def endpoint(self, tenant: str) -> str:
        return f"https://api.lever.co/v0/postings/{tenant}?mode=json"

    def careers_url(self, tenant: str) -> str:
        return f"https://jobs.lever.co/{tenant}"

    @staticmethod
    def _has_jobs_array(payload) -> bool:
        # Lever returns a bare JSON array of postings.
        return isinstance(payload, list)

    def parse(self, payload, tenant: str) -> list[JobRecord]:
        records: list[JobRecord] = []
        for j in payload:
            cats = j.get("categories") or {}
            smin, smax, scur = self._salary(j.get("salaryRange"))
            ats_job_id = str(j["id"])
            vendor_url = j.get("applyUrl") or j.get("hostedUrl")
            records.append(
                JobRecord(
                    ats_job_id=ats_job_id,
                    title=(j.get("text") or "").strip(),
                    description_raw=(j.get("descriptionPlain") or "").strip(),
                    apply_channel=self.resolve_apply(tenant, ats_job_id, vendor_url),
                    location=cats.get("location"),
                    remote_hint=self._remote_hint(j, cats),
                    salary_min=smin,
                    salary_max=smax,
                    salary_currency=scur,
                    posted_at=_epoch_ms_to_dt(j.get("createdAt")),
                    updated_at=_epoch_ms_to_dt(j.get("createdAt")),
                )
            )
        return records

    @staticmethod
    def _remote_hint(j, cats) -> str:
        wt = str(j.get("workplaceType") or "").lower()
        if wt in ("remote", "hybrid", "onsite"):
            return wt
        loc = str(cats.get("location") or "").lower()
        if "remote" in loc:
            return "remote"
        return "unknown"

    @staticmethod
    def _salary(sr):
        if not isinstance(sr, dict):
            return None, None, None
        try:
            smin = int(sr["min"]) if sr.get("min") is not None else None
            smax = int(sr["max"]) if sr.get("max") is not None else None
        except (ValueError, TypeError):
            smin = smax = None
        return smin, smax, sr.get("currency")
