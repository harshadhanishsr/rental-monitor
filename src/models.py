from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict


@dataclass
class Listing:
    id: str
    source: str
    title: str
    address: str
    price: int
    url: str
    furnishing: str = "unknown"
    bachelors_allowed: bool | None = None
    rating: float | None = None
    review_snippet: str | None = None
    images: list[str] = field(default_factory=list)
    lat: float | None = None
    lng: float | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, data: str) -> Listing:
        return cls(**json.loads(data))
