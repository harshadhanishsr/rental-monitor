import pytest
from typing import AsyncIterator
from src.core.engine import run_cycle, EngineConfig
from src.models import Listing
from src.sources.base import SourceAdapter, SourceCtx, RateLimit


class FakeSource(SourceAdapter):
    name = "fake"
    rate = RateLimit(rate=100, burst=10)

    async def scrape(self, ctx: SourceCtx) -> AsyncIterator[Listing]:
        for i in range(3):
            yield Listing(id=f"f{i}", source="fake", title="1BHK",
                          address="Pallavaram, Chennai", price=10000 + i,
                          url=f"https://f/{i}", lat=12.97, lng=80.18)


@pytest.mark.asyncio
async def test_engine_streams_and_dedups(tmp_path, monkeypatch):
    monkeypatch.setenv("OFFICE_LAT", "12.97")
    monkeypatch.setenv("OFFICE_LNG", "80.18")
    cfg = EngineConfig(db_path=tmp_path / "t.db",
                       sources=[FakeSource()], deadline_s=10,
                       alert_fn=None)  # dry-run
    stats = await run_cycle(cfg)
    assert stats.raw_count == 3
    assert stats.after_dedup >= 1
