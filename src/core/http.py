from __future__ import annotations
import httpx
from tenacity import (AsyncRetrying, retry_if_exception_type,
                      stop_after_attempt, wait_exponential_jitter)

_DEFAULT_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0.0.0 Safari/537.36"),
    "Accept-Language": "en-IN,en;q=0.9",
}


class _RetryStatus(Exception):
    def __init__(self, response: httpx.Response):
        self.response = response


class AsyncHttp:
    def __init__(self, *, retries: int = 3, backoff_base: float = 1.0,
                 timeout: float = 25.0, proxy: str | None = None):
        self._client = httpx.AsyncClient(
            http2=True, follow_redirects=True, timeout=timeout,
            headers=_DEFAULT_HEADERS, proxy=proxy,
        )
        self._retrying = AsyncRetrying(
            stop=stop_after_attempt(retries),
            wait=wait_exponential_jitter(initial=backoff_base, max=8),
            retry=retry_if_exception_type((httpx.TransportError, _RetryStatus)),
            reraise=True,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self._client.aclose()

    async def get(self, url: str, **kw) -> httpx.Response:
        async for attempt in self._retrying:
            with attempt:
                r = await self._client.get(url, **kw)
                if r.status_code in (429, 502, 503, 504):
                    raise _RetryStatus(r)
                return r
        raise RuntimeError("unreachable")
