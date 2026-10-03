import httpx
import pytest
from src.core.http import AsyncHttp


@pytest.mark.asyncio
async def test_retries_on_5xx(respx_mock):
    route = respx_mock.get("https://example.com/").mock(side_effect=[
        httpx.Response(503), httpx.Response(503), httpx.Response(200, text="ok")
    ])
    async with AsyncHttp(retries=3, backoff_base=0) as http:
        r = await http.get("https://example.com/")
    assert r.status_code == 200
    assert route.call_count == 3
