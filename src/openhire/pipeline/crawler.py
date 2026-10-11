"""Async fetch orchestration with politeness controls.

Politeness (README §数据源):
  * global concurrency ≤ MAX_GLOBAL_CONCURRENCY (default 5)
  * a given tenant is never hit more than once per MIN_TENANT_INTERVAL_MINUTES (30)

The 30-minute floor is enforced by `due_companies()` at the DB layer (last_crawled_at);
this module enforces the global concurrency cap for a single crawl batch.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx

from .. import config
from ..ats import FetchResult, get_client


@dataclass
class CompanyRef:
    id: str
    ats_vendor: str
    ats_tenant: str
    name: str


async def fetch_all(
    companies: list[CompanyRef],
    concurrency: int | None = None,
    on_result=None,
) -> dict[str, FetchResult]:
    """Fetch every company concurrently under a global semaphore.

    `on_result(company, result)` is invoked as each completes (for progress display).
    """
    concurrency = concurrency or config.MAX_GLOBAL_CONCURRENCY
    sem = asyncio.Semaphore(concurrency)
    results: dict[str, FetchResult] = {}

    headers = {"User-Agent": config.USER_AGENT, "Accept": "application/json"}
    timeout = httpx.Timeout(config.HTTP_TIMEOUT_SECONDS)

    async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:

        async def one(company: CompanyRef):
            async with sem:
                client_impl = get_client(company.ats_vendor)
                result = await client_impl.fetch(client, company.ats_tenant)
            results[company.id] = result
            if on_result:
                on_result(company, result)

        await asyncio.gather(*(one(c) for c in companies))

    return results


def fetch_board(vendor: str, tenant: str) -> FetchResult:
    """One live read of one board for `service.read_board` (reports/069): the crawler's own
    client settings and headers, one tenant, no database. Works whether or not the calling
    thread already runs an event loop (the MCP server does; the CLI may), by running the
    read on a private loop in a worker thread when it must."""
    headers = {"User-Agent": config.USER_AGENT, "Accept": "application/json"}
    timeout = httpx.Timeout(config.HTTP_TIMEOUT_SECONDS)

    async def _go() -> FetchResult:
        async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
            return await get_client(vendor).fetch(client, tenant)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_go())
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(lambda: asyncio.run(_go())).result()
