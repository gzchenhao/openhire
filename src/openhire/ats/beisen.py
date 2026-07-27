"""Beisen (北森) recruitment-portal API — the ATS behind `<tenant>.zhiye.com`.

POST https://{tenant}.zhiye.com/api/Jobad/GetJobAdPageList
     {"PageIndex":0,"PageSize":50,"Category":["1"],"KeyWords":"","SpecialType":0,
      "PortalId":"","DisplayFields":["Category","Kind","LocId","PostDate","Salary"]}

Two things differ from the Western vendors and drive this module's shape:

* It is a **POST** with a JSON body and it **pages**, so `fetch()` is overridden rather
  than reusing the base GET. `DisplayFields` is not cosmetic: without it the response
  omits PostDate/LocNames/Salary entirely (they come back null), so it is mandatory.
* `Category:["1"]` selects 社会招聘 (experienced hire). 校招 (campus) postings are new-grad
  funnels and are deliberately excluded.

Politeness: pages within a tenant are fetched sequentially, and a module-level semaphore
caps concurrent Beisen tenants at 2 — stricter than the global cap, per the domestic-ATS
rate-limit policy. The 30-minute per-tenant floor is enforced upstream by `due_companies()`.

This endpoint is public and unauthenticated: no cookie, no token, no signature.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import re

import httpx

from .base import ATSClient, FetchResult, JobRecord, html_to_text

# Domestic ATS politeness: at most 2 Beisen tenants in flight at once.
_BEISEN_SEMAPHORE = asyncio.Semaphore(2)

_PAGE_SIZE = 50
_MAX_PAGES = 40  # 2,000 postings per tenant — far above any observed roster

# Fields the portal only populates when explicitly requested.
_DISPLAY_FIELDS = ["Category", "Kind", "LocId", "PostDate", "Salary", "WorkWeChatQrCode"]

# Beisen serialises "no date" as year 1 rather than null.
_NULL_DATE_PREFIX = "0001-01-01"
# Beijing time: the portal's naive timestamps are local to the tenant.
_CN_TZ = dt.timezone(dt.timedelta(hours=8))

# "25K-50K 元/月" · "12K-20K元/月" · "25-50K" — monthly CNY, as published.
_SALARY_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*[Kk]?\s*[-–~至]\s*(\d+(?:\.\d+)?)\s*([KkWw万])?", re.UNICODE
)


class BeisenClient(ATSClient):
    vendor = "beisen"

    def endpoint(self, tenant: str) -> str:
        return f"https://{tenant}.zhiye.com/api/Jobad/GetJobAdPageList"

    def careers_url(self, tenant: str) -> str:
        return f"https://{tenant}.zhiye.com/social/jobs"

    @staticmethod
    def _has_jobs_array(payload) -> bool:
        return isinstance(payload, dict) and isinstance(payload.get("Data"), list)

    # --- fetch (POST + pagination) --------------------------------------------
    def _body(self, page: int) -> dict:
        return {
            "PageIndex": page,
            "PageSize": _PAGE_SIZE,
            "Category": ["1"],
            "KeyWords": "",
            "SpecialType": 0,
            "PortalId": "",
            "DisplayFields": list(_DISPLAY_FIELDS),
        }

    async def fetch(self, client: httpx.AsyncClient, tenant: str) -> FetchResult:
        """Page through a tenant's 社招 postings. Valid only on HTTP 200 + a Data array."""
        url = self.endpoint(tenant)
        headers = {"Referer": self.careers_url(tenant), "Content-Type": "application/json"}
        rows: list[dict] = []

        async with _BEISEN_SEMAPHORE:
            for page in range(_MAX_PAGES):
                try:
                    resp = await client.post(url, json=self._body(page), headers=headers)
                except httpx.HTTPError as exc:
                    if rows:  # keep what we already have; a partial roster still beats none
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

                batch = payload["Data"]
                rows.extend(batch)
                total = payload.get("Count")
                if len(batch) < _PAGE_SIZE:
                    break
                if isinstance(total, int) and len(rows) >= total:
                    break

        try:
            records = self.parse({"Data": rows}, tenant)
        except Exception as exc:  # a malformed record set should not kill the crawl
            return FetchResult(ok=False, status=200, error=f"parse error: {exc}")

        return FetchResult(ok=True, status=200, records=records)

    # --- parsing ---------------------------------------------------------------
    def parse(self, payload, tenant: str) -> list[JobRecord]:
        records: list[JobRecord] = []
        for j in payload["Data"]:
            # The GUID `Id` — not the numeric JobAdId — is what the portal deep-links with.
            ats_job_id = str(j.get("Id") or "").strip()
            if not ats_job_id:
                continue
            smin, smax, scur = self._salary(j.get("Salary"))
            location = self._location(j)
            records.append(
                JobRecord(
                    ats_job_id=ats_job_id,
                    title=(j.get("JobAdName") or "").strip(),
                    description_raw=self._description(j),
                    apply_channel=self.resolve_apply(tenant, ats_job_id, None),
                    location=location,
                    remote_hint=self._remote_hint(j, location),
                    salary_min=smin,
                    salary_max=smax,
                    salary_currency=scur,
                    posted_at=self._date(j.get("PostDateInt"), j.get("PostDate")),
                    updated_at=self._date(None, j.get("ChangeDate")),
                )
            )
        return records

    @staticmethod
    def _description(j: dict) -> str:
        """职责 (Duty) + 任职要求 (Require) — the two halves of a Chinese JD."""
        parts = []
        for key in ("Duty", "Require"):
            val = j.get(key)
            if val:
                parts.append(html_to_text(str(val)))
        return "\n\n".join(p for p in parts if p).strip()

    @staticmethod
    def _location(j: dict) -> str | None:
        names = j.get("LocNames")
        if isinstance(names, list) and names:
            return " / ".join(str(n) for n in names if n) or None
        return None

    @staticmethod
    def _remote_hint(j: dict, location: str | None) -> str:
        """Beisen has no workplace-type field; only an explicit 远程 marker is trusted."""
        blob = f"{j.get('JobAdName') or ''} {location or ''} {j.get('Kind') or ''}"
        if "远程" in blob or "remote" in blob.lower():
            return "remote"
        return "unknown"

    @staticmethod
    def _date(epoch_ms, raw) -> dt.datetime | None:
        """Real ATS publish date, or None.

        Beisen writes year-1 dates and 0 epochs for "never published"; those become NULL
        rather than the crawl time — a fabricated datePosted is worse than a missing one.
        """
        if epoch_ms:
            try:
                return dt.datetime.fromtimestamp(int(epoch_ms) / 1000, tz=dt.timezone.utc)
            except (ValueError, OSError, TypeError):
                pass
        if not raw or not isinstance(raw, str) or raw.startswith(_NULL_DATE_PREFIX):
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
    def _salary(raw) -> tuple[int | None, int | None, str | None]:
        """Parse "25K-50K 元/月" as published — monthly CNY, never annualised.

        Callers must treat CNY figures as the employer's stated monthly figure; inventing
        an annual number (×12? ×13? ×16?) would be fabrication, so we do not.
        """
        if not raw or not isinstance(raw, str):
            return None, None, None
        m = _SALARY_RE.search(raw)
        if not m:
            return None, None, None
        lo_s, hi_s, unit = m.group(1), m.group(2), m.group(3)
        # A trailing unit applies to both bounds ("25-50K"); 万 = 10,000, K = 1,000.
        if unit in ("W", "w", "万"):
            mult = 10000
        elif unit in ("K", "k"):
            mult = 1000
        else:
            mult = 1000 if "K" in raw or "k" in raw else 1
        try:
            lo, hi = int(float(lo_s) * mult), int(float(hi_s) * mult)
        except (ValueError, TypeError):
            return None, None, None
        if lo <= 0 or hi <= 0 or hi < lo:
            return None, None, None
        return lo, hi, "CNY"
