"""Ashby public job-board API.

GET https://api.ashbyhq.com/posting-api/job-board/{jobBoardName}?includeCompensation=true
"""

from __future__ import annotations

from .base import ATSClient, JobRecord, _iso_to_dt, html_to_text


class AshbyClient(ATSClient):
    vendor = "ashby"

    def endpoint(self, tenant: str) -> str:
        return (
            f"https://api.ashbyhq.com/posting-api/job-board/{tenant}"
            "?includeCompensation=true"
        )

    def careers_url(self, tenant: str) -> str:
        return f"https://jobs.ashbyhq.com/{tenant}"

    @staticmethod
    def _has_jobs_array(payload) -> bool:
        return isinstance(payload, dict) and isinstance(payload.get("jobs"), list)

    def parse(self, payload, tenant: str) -> list[JobRecord]:
        records: list[JobRecord] = []
        for j in payload["jobs"]:
            if j.get("isListed") is False:
                continue
            desc = j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml"))
            smin, smax, scur = self._salary(j.get("compensation"))
            ats_job_id = str(j["id"])
            vendor_url = j.get("applyUrl") or j.get("jobUrl")
            records.append(
                JobRecord(
                    ats_job_id=ats_job_id,
                    title=(j.get("title") or "").strip(),
                    description_raw=(desc or "").strip(),
                    apply_channel=self.resolve_apply(tenant, ats_job_id, vendor_url),
                    location=j.get("location"),
                    remote_hint=self._remote_hint(j),
                    salary_min=smin,
                    salary_max=smax,
                    salary_currency=scur,
                    posted_at=_iso_to_dt(j.get("publishedAt")),
                    updated_at=_iso_to_dt(j.get("publishedAt")),
                )
            )
        return records

    @staticmethod
    def _remote_hint(j) -> str:
        wt = str(j.get("workplaceType") or "").lower()
        if wt in ("remote", "hybrid", "onsite"):
            return wt
        if j.get("isRemote") is True:
            return "remote"
        loc = str(j.get("location") or "").lower()
        if "remote" in loc:
            return "remote"
        return "unknown"

    @staticmethod
    def _salary(comp):
        if not isinstance(comp, dict):
            return None, None, None
        for tier in comp.get("compensationTiers") or []:
            for c in tier.get("components") or []:
                if str(c.get("compensationType", "")).lower() == "salary":
                    try:
                        smin = int(c["minValue"]) if c.get("minValue") is not None else None
                        smax = int(c["maxValue"]) if c.get("maxValue") is not None else None
                    except (ValueError, TypeError):
                        smin = smax = None
                    return smin, smax, c.get("currencyCode")
        return None, None, None
