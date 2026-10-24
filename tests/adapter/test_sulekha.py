import logging
import httpx
import pytest
from pathlib import Path
from src.core.circuit import Breaker
from src.core.http import AsyncHttp
from src.core.ratelimit import TokenBucket
from src.sources.base import SourceCtx
from src.sources.sulekha import Sulekha

FIXTURE = Path("tests/fixtures/sulekha/pallavaram.html").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_sulekha_parses_fixture(respx_mock):
    respx_mock.get(host="property.sulekha.com").mock(
        return_value=httpx.Response(200, text=FIXTURE))
    async with AsyncHttp() as http:
        ctx = SourceCtx(http=http, bucket=TokenBucket(100, 10), breaker=Breaker(),
                        logger=logging.getLogger("test"), config=None)
        listings = [l async for l in Sulekha().scrape(ctx)]
    assert len(listings) > 0
    assert all(l.source == "sulekha" for l in listings)
    assert all(l.price > 0 for l in listings)
