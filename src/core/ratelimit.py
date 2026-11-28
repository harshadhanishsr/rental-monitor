import asyncio
import time


class TokenBucket:
    def __init__(self, rate: float, burst: int):
        self.rate, self.capacity = rate, burst
        self.tokens = float(burst)
        self.updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
            if self.tokens < 1:
                await asyncio.sleep((1 - self.tokens) / self.rate)
                self.tokens = 0
                # Reset updated AFTER the sleep so the time we spent waiting
                # is not credited as refill on the next acquire (otherwise the
                # bucket would silently let burst+1 through every wait window).
                self.updated = time.monotonic()
            else:
                self.tokens -= 1
                self.updated = now
