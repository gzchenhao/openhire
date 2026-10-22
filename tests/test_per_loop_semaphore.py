"""Module-level asyncio primitives must not cross event loops (0.8.26).

`ohp ingest --seed` checks the seeds with one asyncio.run() and crawls with another. The
Moka adapter's module-level Semaphore had bound itself to the first loop when three tenants
contended for its two slots, and the crawl of 15 Hong Kong employers on 2026-10-22 died with
"Semaphore ... is bound to a different event loop". Each loop now gets its own semaphore.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from openhire.ats import beisen, lixiang, moka
from openhire.ats.base import PerLoopSemaphore


def _contend(sem, n: int = 3) -> None:
    async def one():
        async with sem:
            await asyncio.sleep(0.01)

    async def main():
        await asyncio.gather(*(one() for _ in range(n)))

    asyncio.run(main())


def test_a_plain_semaphore_shared_across_two_loops_fails():
    """The failure this guards against, so the next test is known to exercise it."""
    sem = asyncio.Semaphore(1)
    _contend(sem)
    with pytest.raises(RuntimeError, match="different event loop"):
        _contend(sem)


def test_per_loop_semaphore_survives_a_second_loop():
    sem = PerLoopSemaphore(1)
    _contend(sem)
    _contend(sem)  # the second asyncio.run() is the one that used to raise


def test_per_loop_semaphore_still_limits_concurrency_within_a_loop():
    sem = PerLoopSemaphore(2)
    active = peak = 0

    async def one():
        nonlocal active, peak
        async with sem:
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1

    async def main():
        await asyncio.gather(*(one() for _ in range(6)))

    asyncio.run(main())
    assert peak == 2


def test_the_vendor_adapters_use_per_loop_semaphores():
    assert isinstance(moka._MOKA_SEMAPHORE, PerLoopSemaphore)
    assert isinstance(beisen._BEISEN_SEMAPHORE, PerLoopSemaphore)
    assert isinstance(lixiang._LIXIANG_SEMAPHORE, PerLoopSemaphore)


def test_no_module_level_asyncio_primitive_anywhere_in_the_package():
    root = Path(__file__).resolve().parents[1] / "src" / "openhire"
    pattern = re.compile(
        r"^[A-Za-z_][A-Za-z0-9_]*\s*(?::[^=]+)?=\s*asyncio\.(Semaphore|BoundedSemaphore|Lock|Event|Condition|Queue)\(",
        re.M,
    )
    offenders = sorted(str(p.relative_to(root)) for p in root.rglob("*.py")
                       if pattern.search(p.read_text(encoding="utf-8")))
    assert not offenders, f"module-level asyncio primitives bind to one event loop: {offenders}"


def test_two_crawls_of_three_moka_tenants_in_one_process(monkeypatch):
    """The 2026-10-22 failure end to end: three Moka tenants contend for the adapter's two
    slots in one crawl, then a second crawl runs on a new loop in the same process, as
    `ohp ingest --seed` does after its seed check."""
    import httpx

    from openhire.pipeline import crawler

    async def handler(request):
        await asyncio.sleep(0.01)  # hold the slot long enough for the third tenant to wait
        return httpx.Response(404, text="gone")

    real_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient",
                        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    refs = [crawler.CompanyRef(id=f"m{i}", ats_vendor="moka", ats_tenant=f"org{i}/{i}", name=f"M{i}")
            for i in range(3)]
    for _ in range(2):
        results = asyncio.run(crawler.fetch_all(refs))
        assert sorted(results) == ["m0", "m1", "m2"]
        assert all(not r.ok and r.status == 404 for r in results.values())
