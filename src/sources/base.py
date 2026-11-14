from __future__ import annotations
import abc
from dataclasses import dataclass
from typing import AsyncIterator, ClassVar
from src.core.circuit import Breaker
from src.core.http import AsyncHttp
from src.core.ratelimit import TokenBucket
from src.models import Listing


@dataclass
class RateLimit:
    rate: float = 1.0     # req/s
    burst: int = 3


@dataclass
class SourceCtx:
    http: AsyncHttp
    bucket: TokenBucket
    breaker: Breaker
    logger: object
    config: object
    browser: object | None = None  # lazy Playwright


class SourceAdapter(abc.ABC):
    name: ClassVar[str] = "abstract"
    rate: ClassVar[RateLimit] = RateLimit()
    timeout_s: ClassVar[float] = 25.0
    needs_browser: ClassVar[bool] = False

    @abc.abstractmethod
    async def scrape(self, ctx: SourceCtx) -> AsyncIterator[Listing]: ...
