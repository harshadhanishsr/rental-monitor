from __future__ import annotations
from pydantic import BaseModel, Field, PositiveInt, ConfigDict


class Listing(BaseModel):
    model_config = ConfigDict(frozen=False, str_strip_whitespace=True)

    id: str
    source: str
    title: str
    address: str
    price: PositiveInt
    url: str
    furnishing: str = "unknown"
    bachelors_allowed: bool | None = None
    rating: float | None = None
    review_snippet: str | None = None
    images: list[str] = Field(default_factory=list)
    lat: float | None = None
    lng: float | None = None
    also_seen_on: list[str] = Field(default_factory=list)
    fingerprint: str | None = None


class RunStats(BaseModel):
    started_at: int
    duration_ms: int = 0
    raw_count: int = 0
    after_filter: int = 0
    after_dedup: int = 0
    alerted: int = 0
    per_source: dict[str, dict[str, int | str]] = Field(default_factory=dict)
    breaker_open: list[str] = Field(default_factory=list)
