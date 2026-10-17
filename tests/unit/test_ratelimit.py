import time
import pytest
from src.core.ratelimit import TokenBucket


@pytest.mark.asyncio
async def test_bucket_throttles():
    b = TokenBucket(rate=10, burst=2)  # 10/s
    start = time.monotonic()
    for _ in range(4):
        await b.acquire()
    # 2 free + 2 throttled at 10/s = ~0.2s
    assert time.monotonic() - start >= 0.15
