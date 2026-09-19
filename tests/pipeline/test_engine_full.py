"""Engine resilience: one source crashing must not abort the cycle.

A real cycle may have a flaky adapter (anti-bot challenge, transient 5xx, JSON
shape change). The engine isolates each source in a TaskGroup-managed task
that swallows exceptions and records them in ``stats.per_source[*].errored``.
This test verifies that contract with a fake crashing source alongside
two healthy ones.
"""
import pytest
from typing import AsyncIterator
from src.core.engine import run_cycle, EngineConfig
from src.models import Listing
from src.sources.base import SourceAdapter, SourceCtx, RateLimit


class _OkSource(SourceAdapter):
    rate = RateLimit(rate=100, burst=10)

    def __init__(self, name: str, n: int):
        self._n = n
        type(self).name = name  # classvar shadowed per-instance via subclass

    async def scrape(self, ctx: SourceCtx) -> AsyncIterator[Listing]:
        for i in range(self._n):
            yield Listing(
                id=f"{self.name}_{i}", source=self.name,
                title="1BHK", address=f"Area{i}, Chennai",
                price=10000 + i, url=f"https://example.test/{self.name}/{i}",
                lat=12.97 + i * 0.001, lng=80.18 + i * 0.001,
            )


def _ok_factory(name: str, n: int) -> SourceAdapter:
    cls = type(f"Ok_{name}", (_OkSource,), {"name": name})
    return cls(name, n)


class CrashSource(SourceAdapter):
    name = "crasher"
    rate = RateLimit(rate=100, burst=10)

    async def scrape(self, ctx: SourceCtx) -> AsyncIterator[Listing]:
        # Yield once so the partial output is preserved, then explode.
        yield Listing(
            id="crasher_0", source="crasher", title="1BHK",
            address="X, Chennai", price=12000, url="https://x.test/0",
            lat=12.97, lng=80.18,
        )
        raise RuntimeError("simulated upstream failure")


@pytest.mark.asyncio
async def test_engine_survives_single_source_crash(tmp_path, monkeypatch):
    monkeypatch.setenv("OFFICE_LAT", "12.97")
    monkeypatch.setenv("OFFICE_LNG", "80.18")
    sources = [_ok_factory("alpha", 3), CrashSource(), _ok_factory("beta", 2)]
    cfg = EngineConfig(db_path=tmp_path / "t.db", sources=sources,
                       deadline_s=10, alert_fn=None)
    stats = await run_cycle(cfg)

    # The healthy sources' listings + the crasher's pre-crash yield all arrive.
    assert stats.raw_count == 3 + 1 + 2
    assert stats.after_dedup >= 1
    # Per-source bookkeeping records the failure without aborting the cycle.
    assert stats.per_source["crasher"]["errored"] == 1
    assert stats.per_source["alpha"]["errored"] == 0
    assert stats.per_source["beta"]["errored"] == 0


def test_registry_lists_only_working_adapters():
    """The registry must exclude deferred adapters until they're wired."""
    from src.sources.registry import all_sources
    names = {s.name for s in all_sources()}
    assert names == {"sulekha", "squareyards", "99acres",
                     "magicbricks", "olx", "duckduckgo"}
