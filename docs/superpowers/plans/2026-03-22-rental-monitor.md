# Rental Space Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Dockerized Python service that scrapes 6 rental platforms every hour, filters listings for 1 BHK near Chromepet/Mimillichery Chennai within ₹15K, and sends WhatsApp alerts via Twilio.

**Architecture:** APScheduler triggers an hourly run cycle that fans out to 6 independent Playwright scrapers, applies property + distance filters, deduplicates against SQLite, and sends Twilio WhatsApp messages with images. Pending alerts that fail are retried every hour for up to 48 attempts.

**Tech Stack:** Python 3.11 · Playwright · APScheduler · geopy (Nominatim) · haversine · Twilio SDK · SQLite · Docker + docker-compose

---

## File Structure

```
rental-monitor/
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── requirements.txt
├── main.py                          # entrypoint: health-check → start scheduler
├── src/
│   ├── __init__.py
│   ├── models.py                    # Listing dataclass
│   ├── db.py                        # SQLite init + all CRUD operations
│   ├── filters/
│   │   ├── __init__.py
│   │   ├── property_filter.py       # 1BHK + price + bachelor filter
│   │   └── distance_filter.py       # geocode + haversine + zone assignment
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── base.py                  # shared Playwright browser context factory
│   │   ├── nobroker.py
│   │   ├── magicbricks.py
│   │   ├── acres99.py
│   │   ├── olx.py
│   │   ├── housing.py
│   │   └── quikr.py
│   ├── notifier/
│   │   ├── __init__.py
│   │   └── whatsapp.py              # Twilio send + startup health-check
│   └── scheduler.py                 # APScheduler run cycle orchestration
├── tests/
│   ├── conftest.py                  # shared fixtures (in-memory DB, env vars)
│   ├── test_models.py
│   ├── test_db.py
│   ├── test_property_filter.py
│   ├── test_distance_filter.py
│   ├── test_notifier.py
│   └── test_scheduler.py
└── data/                            # runtime volume: rental_monitor.db lives here
```

**Scraper design note:** Each scraper is split into two layers:
1. Pure parsing helpers (extract ID from URL, parse price from text) — fully unit-testable
2. Thin Playwright browser layer (`scrape()`) — not unit-tested; verified manually on first run

---

## Task 1: Project Scaffold

**Files:**
- Create: `requirements.txt`
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `src/__init__.py`
- Create: `tests/__init__.py`
- Create: `main.py` (stub only — implemented in Task 15)

- [ ] **Step 1: Create `requirements.txt`**

```
playwright==1.43.0
APScheduler==3.10.4
geopy==2.4.1
haversine==2.8.1
twilio==9.0.5
python-dotenv==1.0.1
pytest==8.1.1
pytest-mock==3.14.0
```

- [ ] **Step 2: Create `Dockerfile`**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    wget curl gnupg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium --with-deps

COPY . .

RUN mkdir -p /app/data

CMD ["python", "main.py"]
```

- [ ] **Step 3: Create `docker-compose.yml`**

```yaml
version: "3.9"

services:
  rental-monitor:
    build: .
    restart: always
    env_file: .env
    volumes:
      - ./data:/app/data
```

- [ ] **Step 4: Create `.env.example`**

```
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
WHATSAPP_TO=whatsapp:+918610385533
OFFICE_LAT=12.9698
OFFICE_LNG=80.1409
```

- [ ] **Step 5: Create empty `src/__init__.py` and `tests/__init__.py`**

```python
# empty
```

- [ ] **Step 6: Create stub `main.py`**

```python
# Implemented in Task 15
if __name__ == "__main__":
    pass
```

- [ ] **Step 7: Commit**

```bash
git add requirements.txt Dockerfile docker-compose.yml .env.example src/__init__.py tests/__init__.py main.py
git commit -m "feat: project scaffold"
```

---

## Task 2: Listing Dataclass

**Files:**
- Create: `src/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models.py
import json
from src.models import Listing

def test_listing_defaults():
    listing = Listing(
        id="123",
        source="nobroker",
        title="1 BHK in Chromepet",
        address="Chromepet, Chennai",
        price=12000,
        url="https://nobroker.in/property/123",
    )
    assert listing.furnishing == "unknown"
    assert listing.bachelors_allowed is None
    assert listing.rating is None
    assert listing.review_snippet is None
    assert listing.images == []
    assert listing.lat is None
    assert listing.lng is None

def test_listing_to_json_roundtrip():
    listing = Listing(
        id="456",
        source="olx",
        title="1BHK flat",
        address="Mimillichery",
        price=10000,
        url="https://olx.in/item/456",
        furnishing="furnished",
        bachelors_allowed=True,
        rating=4.2,
        review_snippet="Great place",
        images=["https://img1.jpg", "https://img2.jpg"],
        lat=12.97,
        lng=80.14,
    )
    data = json.loads(listing.to_json())
    assert data["id"] == "456"
    assert data["price"] == 10000
    assert data["images"] == ["https://img1.jpg", "https://img2.jpg"]

def test_listing_from_json():
    original = Listing(
        id="789", source="magicbricks", title="BHK",
        address="Chromepet", price=13500, url="https://mb.com/789",
    )
    restored = Listing.from_json(original.to_json())
    assert restored.id == "789"
    assert restored.price == 13500
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /c/Users/harsh/projects/rental-monitor
python -m pytest tests/test_models.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.models'`

- [ ] **Step 3: Implement `src/models.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_models.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add src/models.py tests/test_models.py
git commit -m "feat: Listing dataclass with JSON serialization"
```

---

## Task 3: Database Layer

**Files:**
- Create: `src/db.py`
- Create: `tests/test_db.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create `tests/conftest.py` with in-memory DB fixture**

```python
# tests/conftest.py
import os
import pytest
import sqlite3
from src.db import init_db, get_connection

@pytest.fixture
def db_conn():
    """In-memory SQLite connection for tests."""
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    yield conn
    conn.close()
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_db.py
import json
from datetime import datetime, timezone
from src.db import init_db, is_seen, mark_seen, add_pending_alert, get_pending_alerts, resolve_pending_alert, increment_retry, delete_stale_pending, cache_geocode, get_cached_geocode
from src.models import Listing


def make_listing(**kwargs):
    defaults = dict(id="1", source="nobroker", title="T", address="A", price=12000, url="http://x.com")
    return Listing(**{**defaults, **kwargs})


def test_is_seen_false_initially(db_conn):
    assert is_seen(db_conn, "1", "nobroker") is False


def test_mark_seen_and_is_seen(db_conn):
    mark_seen(db_conn, "1", "nobroker")
    assert is_seen(db_conn, "1", "nobroker") is True


def test_different_source_not_seen(db_conn):
    mark_seen(db_conn, "1", "nobroker")
    assert is_seen(db_conn, "1", "olx") is False


def test_add_and_get_pending_alert(db_conn):
    listing = make_listing(id="99", source="olx")
    add_pending_alert(db_conn, listing, "PREFERRED", 3.2)
    rows = get_pending_alerts(db_conn)
    assert len(rows) == 1
    row_id, restored, zone, distance_km = rows[0]
    assert restored.id == "99"
    assert restored.source == "olx"
    assert zone == "PREFERRED"
    assert distance_km == 3.2


def test_resolve_pending_alert(db_conn):
    listing = make_listing(id="42", source="quikr")
    add_pending_alert(db_conn, listing, "ACCEPTABLE", 7.0)
    row_id, _, _, _ = get_pending_alerts(db_conn)[0]
    resolve_pending_alert(db_conn, row_id)
    assert get_pending_alerts(db_conn) == []


def test_increment_retry(db_conn):
    listing = make_listing()
    add_pending_alert(db_conn, listing, "PREFERRED", 2.0)
    row_id, _, _, _ = get_pending_alerts(db_conn)[0]
    increment_retry(db_conn, row_id)
    rows = get_pending_alerts(db_conn)
    assert rows[0][0] == row_id  # still there


def test_delete_stale_pending(db_conn):
    listing = make_listing()
    add_pending_alert(db_conn, listing, "PREFERRED", 1.5)
    row_id, _, _, _ = get_pending_alerts(db_conn)[0]
    # bump retry_count to 48 manually
    db_conn.execute("UPDATE pending_alerts SET retry_count = 48 WHERE id = ?", (row_id,))
    db_conn.commit()
    delete_stale_pending(db_conn, max_retries=48)
    assert get_pending_alerts(db_conn) == []


def test_geocode_cache_miss(db_conn):
    assert get_cached_geocode(db_conn, "abc123") is None


def test_geocode_cache_hit(db_conn):
    cache_geocode(db_conn, "abc123", 12.97, 80.14)
    result = get_cached_geocode(db_conn, "abc123")
    assert result == (12.97, 80.14)
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
python -m pytest tests/test_db.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.db'`

- [ ] **Step 4: Implement `src/db.py`**

```python
import sqlite3
import json
from datetime import datetime, timezone
from src.models import Listing


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS seen_listings (
            id TEXT NOT NULL,
            source TEXT NOT NULL,
            seen_at TEXT NOT NULL,
            PRIMARY KEY (id, source)
        );

        CREATE TABLE IF NOT EXISTS geocode_cache (
            address_hash TEXT PRIMARY KEY,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            cached_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS pending_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id TEXT NOT NULL,
            source TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            zone TEXT NOT NULL,
            distance_km REAL,
            created_at TEXT NOT NULL,
            retry_count INTEGER DEFAULT 0
        );
    """)
    conn.commit()


def is_seen(conn: sqlite3.Connection, listing_id: str, source: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM seen_listings WHERE id = ? AND source = ?",
        (listing_id, source)
    ).fetchone()
    return row is not None


def mark_seen(conn: sqlite3.Connection, listing_id: str, source: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR IGNORE INTO seen_listings (id, source, seen_at) VALUES (?, ?, ?)",
        (listing_id, source, now)
    )
    conn.commit()


def add_pending_alert(conn: sqlite3.Connection, listing: Listing, zone: str, distance_km: float | None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO pending_alerts (listing_id, source, payload_json, zone, distance_km, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (listing.id, listing.source, listing.to_json(), zone, distance_km, now)
    )
    conn.commit()


def get_pending_alerts(conn: sqlite3.Connection) -> list[tuple[int, Listing, str, float | None]]:
    rows = conn.execute(
        "SELECT id, payload_json, zone, distance_km FROM pending_alerts ORDER BY created_at"
    ).fetchall()
    return [(row[0], Listing.from_json(row[1]), row[2], row[3]) for row in rows]


def resolve_pending_alert(conn: sqlite3.Connection, row_id: int) -> None:
    conn.execute("DELETE FROM pending_alerts WHERE id = ?", (row_id,))
    conn.commit()


def increment_retry(conn: sqlite3.Connection, row_id: int) -> None:
    conn.execute(
        "UPDATE pending_alerts SET retry_count = retry_count + 1 WHERE id = ?",
        (row_id,)
    )
    conn.commit()


def delete_stale_pending(conn: sqlite3.Connection, max_retries: int = 48) -> None:
    conn.execute(
        "DELETE FROM pending_alerts WHERE retry_count >= ?",
        (max_retries,)
    )
    conn.commit()


def cache_geocode(conn: sqlite3.Connection, address_hash: str, lat: float, lng: float) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO geocode_cache (address_hash, lat, lng, cached_at) VALUES (?, ?, ?, ?)",
        (address_hash, lat, lng, now)
    )
    conn.commit()


def get_cached_geocode(conn: sqlite3.Connection, address_hash: str) -> tuple[float, float] | None:
    row = conn.execute(
        "SELECT lat, lng FROM geocode_cache WHERE address_hash = ?",
        (address_hash,)
    ).fetchone()
    return (row[0], row[1]) if row else None
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_db.py -v
```

Expected: `10 passed`

- [ ] **Step 6: Commit**

```bash
git add src/db.py tests/test_db.py tests/conftest.py
git commit -m "feat: SQLite database layer with seen_listings, geocode_cache, pending_alerts"
```

---

## Task 4: Property Filter

**Files:**
- Create: `src/filters/__init__.py`
- Create: `src/filters/property_filter.py`
- Create: `tests/test_property_filter.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_property_filter.py
import pytest
from src.models import Listing
from src.filters.property_filter import passes_property_filter


def make_listing(**kwargs):
    defaults = dict(id="1", source="nobroker", title="1 BHK in Chromepet",
                    address="Chromepet", price=12000, url="http://x.com")
    return Listing(**{**defaults, **kwargs})


def test_valid_listing_passes():
    assert passes_property_filter(make_listing()) is True

def test_price_at_limit_passes():
    assert passes_property_filter(make_listing(price=15000)) is True

def test_price_over_limit_fails():
    assert passes_property_filter(make_listing(price=15001)) is False

def test_non_1bhk_title_fails():
    assert passes_property_filter(make_listing(title="2 BHK in Chromepet")) is False

def test_1bhk_lowercase_passes():
    assert passes_property_filter(make_listing(title="spacious 1bhk flat")) is True

def test_bachelors_none_passes():
    assert passes_property_filter(make_listing(bachelors_allowed=None)) is True

def test_bachelors_true_passes():
    assert passes_property_filter(make_listing(bachelors_allowed=True)) is True

def test_bachelors_false_fails():
    assert passes_property_filter(make_listing(bachelors_allowed=False)) is False

def test_families_only_keyword_in_title_fails():
    assert passes_property_filter(make_listing(title="1 BHK families only")) is False

def test_bachelor_keyword_in_title_sets_allowed():
    listing = make_listing(title="1 BHK bachelor friendly", bachelors_allowed=None)
    assert passes_property_filter(listing) is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_property_filter.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create `src/filters/__init__.py`** (empty)

- [ ] **Step 4: Implement `src/filters/property_filter.py`**

```python
import re
from src.models import Listing

_1BHK_PATTERN = re.compile(r"1\s*bhk", re.IGNORECASE)
_FAMILIES_ONLY = re.compile(r"famil(y|ies)\s*only", re.IGNORECASE)

MAX_PRICE = 15_000


_BACHELOR_KEYWORDS = re.compile(r"\b(bachelor|single|bachelors)\b", re.IGNORECASE)


def passes_property_filter(listing: Listing) -> bool:
    if listing.price > MAX_PRICE:
        return False
    if not _1BHK_PATTERN.search(listing.title):
        return False
    if _FAMILIES_ONLY.search(listing.title):
        return False
    # If platform didn't expose bachelors_allowed, infer from title/description
    if listing.bachelors_allowed is None:
        if _BACHELOR_KEYWORDS.search(listing.title):
            listing.bachelors_allowed = True
    if listing.bachelors_allowed is False:
        return False
    return True
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_property_filter.py -v
```

Expected: `10 passed`

- [ ] **Step 6: Commit**

```bash
git add src/filters/__init__.py src/filters/property_filter.py tests/test_property_filter.py
git commit -m "feat: property filter (1BHK + price + bachelor)"
```

---

## Task 5: Distance Filter

**Files:**
- Create: `src/filters/distance_filter.py`
- Create: `tests/test_distance_filter.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_distance_filter.py
import sqlite3
import pytest
from unittest.mock import patch, MagicMock
from src.db import init_db
from src.models import Listing
from src.filters.distance_filter import assign_zone, geocode_listing, ZONE_PREFERRED, ZONE_ACCEPTABLE, ZONE_FAR


@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    yield conn
    conn.close()


def make_listing(**kwargs):
    defaults = dict(id="1", source="nobroker", title="1 BHK",
                    address="Chromepet Main Road", price=12000, url="http://x.com")
    return Listing(**{**defaults, **kwargs})


def test_zone_preferred():
    assert assign_zone(3.0, 12000, 4.5) == ZONE_PREFERRED

def test_zone_acceptable():
    assert assign_zone(7.5, 12000, None) == ZONE_ACCEPTABLE

def test_zone_far_qualifies():
    assert assign_zone(12.0, 9000, 4.2) == ZONE_FAR

def test_zone_far_price_too_high():
    assert assign_zone(12.0, 11000, 4.5) is None

def test_zone_far_no_rating():
    assert assign_zone(12.0, 9000, None) is None

def test_zone_far_rating_too_low():
    assert assign_zone(12.0, 9000, 3.5) is None

def test_geocode_uses_cache(db_conn):
    from src.db import cache_geocode
    import hashlib
    address = "Chromepet, Chennai"
    address_hash = hashlib.sha256(address.lower().strip().encode()).hexdigest()
    cache_geocode(db_conn, address_hash, 12.97, 80.14)

    with patch("src.filters.distance_filter.Nominatim") as mock_nom:
        result = geocode_listing(address, db_conn)
    mock_nom.assert_not_called()
    assert result == (12.97, 80.14)

def test_geocode_calls_nominatim_on_miss(db_conn):
    mock_location = MagicMock()
    mock_location.latitude = 12.95
    mock_location.longitude = 80.15

    with patch("src.filters.distance_filter.Nominatim") as MockNom:
        MockNom.return_value.geocode.return_value = mock_location
        result = geocode_listing("Some Address, Chennai", db_conn)

    assert result == (12.95, 80.15)

def test_geocode_returns_none_on_failure(db_conn):
    with patch("src.filters.distance_filter.Nominatim") as MockNom:
        MockNom.return_value.geocode.return_value = None
        result = geocode_listing("Unknown Place XYZ", db_conn)
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_distance_filter.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/filters/distance_filter.py`**

```python
import hashlib
import logging
import time
import sqlite3
from geopy.geocoders import Nominatim
from haversine import haversine, Unit
from src.db import cache_geocode, get_cached_geocode
from src.models import Listing

logger = logging.getLogger(__name__)

OFFICE_LAT = None  # loaded from env at runtime
OFFICE_LNG = None

ZONE_PREFERRED = "PREFERRED"
ZONE_ACCEPTABLE = "ACCEPTABLE"
ZONE_FAR = "FAR BUT WORTH IT"

FAR_MAX_PRICE = 10_000
FAR_MIN_RATING = 4.0

_geocoder = None


def _get_geocoder() -> Nominatim:
    global _geocoder
    if _geocoder is None:
        _geocoder = Nominatim(user_agent="rental-monitor/1.0")
    return _geocoder


def _hash_address(address: str) -> str:
    return hashlib.sha256(address.lower().strip().encode()).hexdigest()


def geocode_listing(address: str, conn: sqlite3.Connection) -> tuple[float, float] | None:
    address_hash = _hash_address(address)
    cached = get_cached_geocode(conn, address_hash)
    if cached:
        return cached

    try:
        time.sleep(1)  # Nominatim rate limit: 1 req/sec
        location = _get_geocoder().geocode(f"{address}, Chennai, India")
        if location is None:
            return None
        lat, lng = location.latitude, location.longitude
        cache_geocode(conn, address_hash, lat, lng)
        return (lat, lng)
    except Exception:
        logger.exception("Geocoding failed for address: %s", address)
        return None


def assign_zone(distance_km: float, price: int, rating: float | None) -> str | None:
    if distance_km <= 5.0:
        return ZONE_PREFERRED
    if distance_km <= 10.0:
        return ZONE_ACCEPTABLE
    # FAR zone: price ≤ 10K AND rating ≥ 4.0
    if price <= FAR_MAX_PRICE and rating is not None and rating >= FAR_MIN_RATING:
        return ZONE_FAR
    return None  # do not alert


def apply_distance_filter(
    listings: list[Listing],
    conn: sqlite3.Connection,
    office_lat: float,
    office_lng: float,
) -> list[tuple[Listing, str, float | None]]:
    """
    Returns list of (listing, zone, distance_km) for listings that should be alerted.
    distance_km is None if geocoding failed.
    """
    results = []
    for listing in listings:
        coords = geocode_listing(listing.address, conn)
        if coords is None:
            # geocoding failed — alert without distance
            listing.lat = None
            listing.lng = None
            results.append((listing, "Distance unknown", None))
            continue

        lat, lng = coords
        listing.lat = lat
        listing.lng = lng
        distance_km = haversine((office_lat, office_lng), (lat, lng), unit=Unit.KILOMETERS)
        zone = assign_zone(distance_km, listing.price, listing.rating)
        if zone is not None:
            results.append((listing, zone, distance_km))

    return results
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_distance_filter.py -v
```

Expected: `9 passed`

- [ ] **Step 5: Commit**

```bash
git add src/filters/distance_filter.py tests/test_distance_filter.py
git commit -m "feat: distance filter with geocoding cache and zone assignment"
```

---

## Task 6: WhatsApp Notifier

**Files:**
- Create: `src/notifier/__init__.py`
- Create: `src/notifier/whatsapp.py`
- Create: `tests/test_notifier.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_notifier.py
import os
import pytest
from unittest.mock import MagicMock, patch
from src.models import Listing
from src.notifier.whatsapp import format_message, send_alert, health_check


def make_listing(**kwargs):
    defaults = dict(id="1", source="nobroker", title="1 BHK in Chromepet",
                    address="Chromepet Main Road", price=12000, url="https://nobroker.in/1",
                    furnishing="semi-furnished", bachelors_allowed=True,
                    rating=4.3, review_snippet="Clean, good water supply",
                    images=["https://img1.jpg", "https://img2.jpg"])
    return Listing(**{**defaults, **kwargs})


def test_format_message_preferred():
    listing = make_listing()
    msg = format_message(listing, "PREFERRED", 3.2)
    assert "PREFERRED" in msg
    assert "3.2km" in msg
    assert "₹12,500" in msg or "12,500" in msg or "12500" in msg
    assert "nobroker.in" in msg
    assert "4.3/5" in msg
    assert "Clean, good water supply" in msg

def test_format_message_far():
    listing = make_listing(price=9500, rating=4.1)
    msg = format_message(listing, "FAR BUT WORTH IT", 13.5)
    assert "FAR BUT WORTH IT" in msg
    assert "13.5km" in msg

def test_format_message_distance_unknown():
    listing = make_listing()
    msg = format_message(listing, "Distance unknown", None)
    assert "Distance unknown" in msg
    assert "km" not in msg

def test_format_message_no_rating():
    listing = make_listing(rating=None, review_snippet=None)
    msg = format_message(listing, "PREFERRED", 2.0)
    assert "⭐" not in msg

def test_send_alert_calls_twilio(monkeypatch):
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACtest")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "token")
    monkeypatch.setenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
    monkeypatch.setenv("WHATSAPP_TO", "whatsapp:+918610385533")

    mock_client = MagicMock()
    mock_msg = MagicMock()
    mock_msg.sid = "SMtest123"
    mock_client.messages.create.return_value = mock_msg

    with patch("src.notifier.whatsapp.Client", return_value=mock_client):
        sid = send_alert(make_listing(), "PREFERRED", 3.2)

    assert sid == "SMtest123"
    mock_client.messages.create.assert_called_once()

def test_health_check_returns_true_on_success(monkeypatch):
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACtest")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "token")
    monkeypatch.setenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
    monkeypatch.setenv("WHATSAPP_TO", "whatsapp:+918610385533")

    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(sid="SMhc")

    with patch("src.notifier.whatsapp.Client", return_value=mock_client):
        assert health_check() is True

def test_health_check_returns_false_on_failure(monkeypatch):
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACtest")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "token")
    monkeypatch.setenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
    monkeypatch.setenv("WHATSAPP_TO", "whatsapp:+918610385533")

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("Twilio error")

    with patch("src.notifier.whatsapp.Client", return_value=mock_client):
        assert health_check() is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_notifier.py -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create `src/notifier/__init__.py`** (empty)

- [ ] **Step 4: Implement `src/notifier/whatsapp.py`**

```python
import logging
import os
from datetime import datetime, timezone
from twilio.rest import Client
from src.models import Listing

logger = logging.getLogger(__name__)


def _get_client() -> Client:
    return Client(
        os.environ["TWILIO_ACCOUNT_SID"],
        os.environ["TWILIO_AUTH_TOKEN"],
    )


def format_message(listing: Listing, zone: str, distance_km: float | None) -> str:
    if distance_km is not None:
        header = f"NEW 1BHK — {zone} ({distance_km:.1f}km from office)"
    else:
        header = f"NEW 1BHK — {zone}"

    broker_line = "No broker" if "nobroker" in listing.source.lower() else "Check for broker"
    bachelor_line = "✅ Bachelors allowed" if listing.bachelors_allowed else "ℹ️ Occupancy unspecified"

    lines = [
        header,
        "",
        f"📍 {listing.address}",
        f"💰 ₹{listing.price:,}/month | {listing.furnishing.title()}",
        f"{bachelor_line} | {broker_line}",
    ]

    if listing.rating is not None:
        review = f' — "{listing.review_snippet}"' if listing.review_snippet else ""
        lines.append(f"⭐ {listing.rating}/5{review}")

    lines += [
        f"🌐 Source: {listing.source.title()}",
        f"🔗 {listing.url}",
        "",
        f"Found at: {datetime.now(timezone.utc).strftime('%H:%M, %d %b %Y')} UTC",
    ]
    return "\n".join(lines)


def send_alert(listing: Listing, zone: str, distance_km: float | None) -> str:
    """Send WhatsApp alert. Returns Twilio message SID on success."""
    client = _get_client()
    body = format_message(listing, zone, distance_km)
    from_number = os.environ["TWILIO_WHATSAPP_FROM"]
    to_number = os.environ["WHATSAPP_TO"]

    # Send text message
    msg = client.messages.create(body=body, from_=from_number, to=to_number)

    # Send images (best-effort — don't fail if images are inaccessible)
    for image_url in listing.images[:3]:
        try:
            client.messages.create(
                media_url=[image_url],
                from_=from_number,
                to=to_number,
            )
        except Exception:
            logger.warning("Failed to send image %s for listing %s", image_url, listing.id)

    return msg.sid


def health_check() -> bool:
    """Send a test message. Returns True if delivered, False otherwise."""
    try:
        client = _get_client()
        msg = client.messages.create(
            body="🏠 Rental Monitor is active and watching for listings. (startup check)",
            from_=os.environ["TWILIO_WHATSAPP_FROM"],
            to=os.environ["WHATSAPP_TO"],
        )
        logger.info("Health check passed. SID: %s", msg.sid)
        return True
    except Exception:
        logger.warning(
            "Health check failed — Twilio delivery error. "
            "If your Sandbox session expired, re-send the join message from your phone."
        )
        return False
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_notifier.py -v
```

Expected: `7 passed`

- [ ] **Step 6: Commit**

```bash
git add src/notifier/__init__.py src/notifier/whatsapp.py tests/test_notifier.py
git commit -m "feat: WhatsApp notifier with Twilio, health-check, best-effort image sending"
```

---

## Task 7: Scraper Base

**Files:**
- Create: `src/scrapers/__init__.py`
- Create: `src/scrapers/base.py`

No unit tests for the Playwright browser factory — verified manually during Task 16.

- [ ] **Step 1: Create `src/scrapers/__init__.py`** (empty)

- [ ] **Step 2: Implement `src/scrapers/base.py`**

```python
from contextlib import asynccontextmanager
from playwright.async_api import async_playwright, Browser, BrowserContext


@asynccontextmanager
async def get_browser_context():
    """Yields a Playwright browser context with realistic headers."""
    async with async_playwright() as p:
        browser: Browser = await p.chromium.launch(headless=True)
        context: BrowserContext = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="en-IN",
        )
        try:
            yield context
        finally:
            await browser.close()
```

- [ ] **Step 3: Commit**

```bash
git add src/scrapers/__init__.py src/scrapers/base.py
git commit -m "feat: Playwright browser context factory"
```

---

## Task 8: NoBroker Scraper

**Files:**
- Create: `src/scrapers/nobroker.py`

- [ ] **Step 1: Write tests for NoBroker ID extraction and price parsing**

```python
# tests/test_scrapers.py  (create this file — all scraper helper tests go here)
from src.scrapers.nobroker import extract_id as nb_extract_id, parse_price as nb_parse_price
from src.scrapers.magicbricks import extract_id as mb_extract_id
from src.scrapers.acres99 import extract_id as ac_extract_id
from src.scrapers.olx import extract_id as olx_extract_id
from src.scrapers.housing import extract_id as hc_extract_id
from src.scrapers.quikr import extract_id as qk_extract_id

# NoBroker
def test_nobroker_extract_id():
    assert nb_extract_id("https://www.nobroker.in/property/rental/chennai/12345678") == "12345678"

def test_nobroker_parse_price_with_comma():
    assert nb_parse_price("₹12,500 / month") == 12500

def test_nobroker_parse_price_plain():
    assert nb_parse_price("15000") == 15000

def test_nobroker_parse_price_none_on_invalid():
    assert nb_parse_price("Contact owner") is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_scrapers.py::test_nobroker_extract_id -v
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement `src/scrapers/nobroker.py`**

```python
import asyncio
import logging
import re
from src.models import Listing
from src.scrapers.base import get_browser_context

logger = logging.getLogger(__name__)

SEARCH_URL = (
    "https://www.nobroker.in/property/rental/chennai/Chromepet"
    "?bedroom=1&budget=15000"
)


def extract_id(url: str) -> str:
    return url.rstrip("/").split("/")[-1]


def parse_price(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


async def _scrape_async() -> list[Listing]:
    listings = []
    async with get_browser_context() as ctx:
        page = await ctx.new_page()
        try:
            await page.goto(SEARCH_URL, wait_until="networkidle", timeout=30000)
            cards = await page.query_selector_all(".srpPropertyCard, [data-testid='property-card']")
            for card in cards:
                try:
                    url_el = await card.query_selector("a[href*='/property/']")
                    if not url_el:
                        continue
                    url = await url_el.get_attribute("href")
                    if not url.startswith("http"):
                        url = "https://www.nobroker.in" + url
                    listing_id = extract_id(url)

                    title_el = await card.query_selector(".property-title, h3, h4")
                    title = (await title_el.inner_text()).strip() if title_el else "1 BHK"

                    price_el = await card.query_selector(".price, [data-testid='price']")
                    price_text = (await price_el.inner_text()).strip() if price_el else ""
                    price = parse_price(price_text)
                    if price is None:
                        continue

                    addr_el = await card.query_selector(".location, [data-testid='location']")
                    address = (await addr_el.inner_text()).strip() if addr_el else "Chromepet, Chennai"

                    img_els = await card.query_selector_all("img[src*='nobroker']")
                    images = []
                    for img in img_els[:3]:
                        src = await img.get_attribute("src")
                        if src:
                            images.append(src)

                    listings.append(Listing(
                        id=listing_id,
                        source="nobroker",
                        title=title,
                        address=address,
                        price=price,
                        url=url,
                        images=images,
                    ))
                except Exception:
                    logger.exception("Error parsing NoBroker card")
        finally:
            await page.close()
    return listings


def scrape() -> list[Listing]:
    return asyncio.run(_scrape_async())
```

- [ ] **Step 4: Run ID + price tests to verify they pass**

```bash
python -m pytest tests/test_scrapers.py -k "nobroker" -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add src/scrapers/nobroker.py tests/test_scrapers.py
git commit -m "feat: NoBroker scraper"
```

---

## Task 9: MagicBricks Scraper

**Files:**
- Create: `src/scrapers/magicbricks.py`

- [ ] **Step 1: Add MagicBricks tests to `tests/test_scrapers.py`**

```python
# Add to tests/test_scrapers.py
def test_magicbricks_extract_id_from_path():
    assert mb_extract_id("https://www.magicbricks.com/property-for-rent/1-BHK/PRO12345") == "PRO12345"

def test_magicbricks_extract_id_from_query():
    assert mb_extract_id("https://www.magicbricks.com/msite/propertyDetails?propertyId=67890") == "67890"
```

- [ ] **Step 2: Run to verify they fail**

```bash
python -m pytest tests/test_scrapers.py -k "magicbricks" -v
```

- [ ] **Step 3: Implement `src/scrapers/magicbricks.py`**

```python
import asyncio
import logging
import re
from urllib.parse import urlparse, parse_qs
from src.models import Listing
from src.scrapers.base import get_browser_context

logger = logging.getLogger(__name__)

SEARCH_URL = (
    "https://www.magicbricks.com/property-for-rent/1-BHK-flats-in-Chromepet-Chennai"
    "?proptype=Multistorey-Apartment,Builder-Floor-Apartment,Penthouse,Studio-Apartment"
    "&BudgetMax=15000"
)


def extract_id(url: str) -> str:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    if "propertyId" in qs:
        return qs["propertyId"][0]
    return url.rstrip("/").split("/")[-1]


def parse_price(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


async def _scrape_async() -> list[Listing]:
    listings = []
    async with get_browser_context() as ctx:
        page = await ctx.new_page()
        try:
            await page.goto(SEARCH_URL, wait_until="networkidle", timeout=30000)
            cards = await page.query_selector_all(".mb-srp__card, [data-id]")
            for card in cards:
                try:
                    url_el = await card.query_selector("a")
                    if not url_el:
                        continue
                    url = await url_el.get_attribute("href")
                    if not url.startswith("http"):
                        url = "https://www.magicbricks.com" + url
                    listing_id = extract_id(url)

                    title_el = await card.query_selector(".mb-srp__card--title")
                    title = (await title_el.inner_text()).strip() if title_el else "1 BHK"

                    price_el = await card.query_selector(".mb-srp__card--price")
                    price = parse_price(await price_el.inner_text()) if price_el else None
                    if price is None:
                        continue

                    addr_el = await card.query_selector(".mb-srp__card--locality")
                    address = (await addr_el.inner_text()).strip() if addr_el else "Chromepet, Chennai"

                    img_els = await card.query_selector_all("img")
                    images = [await i.get_attribute("src") for i in img_els[:3] if await i.get_attribute("src")]

                    listings.append(Listing(
                        id=listing_id, source="magicbricks", title=title,
                        address=address, price=price, url=url, images=images,
                    ))
                except Exception:
                    logger.exception("Error parsing MagicBricks card")
        finally:
            await page.close()
    return listings


def scrape() -> list[Listing]:
    return asyncio.run(_scrape_async())
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_scrapers.py -k "magicbricks" -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add src/scrapers/magicbricks.py tests/test_scrapers.py
git commit -m "feat: MagicBricks scraper"
```

---

## Task 10: 99acres Scraper

**Files:**
- Create: `src/scrapers/acres99.py`

- [ ] **Step 1: Add tests to `tests/test_scrapers.py`**

```python
def test_99acres_extract_id():
    assert ac_extract_id("https://www.99acres.com/1-bhk-flat-for-rent-in-chromepet-chennai-ffid-E7654321-1") == "E7654321"

def test_99acres_extract_id_numeric():
    assert ac_extract_id("https://www.99acres.com/property/12345") == "12345"
```

- [ ] **Step 2: Run to verify they fail**

```bash
python -m pytest tests/test_scrapers.py -k "99acres or ac_extract" -v
```

- [ ] **Step 3: Implement `src/scrapers/acres99.py`**

```python
import asyncio
import logging
import re
from src.models import Listing
from src.scrapers.base import get_browser_context

logger = logging.getLogger(__name__)

SEARCH_URL = (
    "https://www.99acres.com/1-bhk-flat-for-rent-in-chromepet-chennai-ffid"
    "?budget_max=15000"
)

_ID_PATTERN = re.compile(r"-([A-Z0-9]+)-\d+$")


def extract_id(url: str) -> str:
    match = _ID_PATTERN.search(url)
    if match:
        return match.group(1)
    return url.rstrip("/").split("/")[-1]


def parse_price(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


async def _scrape_async() -> list[Listing]:
    listings = []
    async with get_browser_context() as ctx:
        page = await ctx.new_page()
        try:
            await page.goto(SEARCH_URL, wait_until="networkidle", timeout=30000)
            cards = await page.query_selector_all(".tuple__wrapper, [class*='projectTuple']")
            for card in cards:
                try:
                    url_el = await card.query_selector("a[href*='99acres.com']")
                    if not url_el:
                        continue
                    url = await url_el.get_attribute("href")
                    if not url.startswith("http"):
                        url = "https://www.99acres.com" + url
                    listing_id = extract_id(url)

                    title_el = await card.query_selector(".tuple__title, h2")
                    title = (await title_el.inner_text()).strip() if title_el else "1 BHK"

                    price_el = await card.query_selector(".tuple__price-details-text, .priceVal")
                    price = parse_price(await price_el.inner_text()) if price_el else None
                    if price is None:
                        continue

                    addr_el = await card.query_selector(".tuple__location-text")
                    address = (await addr_el.inner_text()).strip() if addr_el else "Chromepet, Chennai"

                    img_els = await card.query_selector_all("img[src]")
                    images = [await i.get_attribute("src") for i in img_els[:3] if await i.get_attribute("src")]

                    listings.append(Listing(
                        id=listing_id, source="99acres", title=title,
                        address=address, price=price, url=url, images=images,
                    ))
                except Exception:
                    logger.exception("Error parsing 99acres card")
        finally:
            await page.close()
    return listings


def scrape() -> list[Listing]:
    return asyncio.run(_scrape_async())
```

- [ ] **Step 4: Run tests and commit**

```bash
python -m pytest tests/test_scrapers.py -k "ac_extract" -v
git add src/scrapers/acres99.py tests/test_scrapers.py
git commit -m "feat: 99acres scraper"
```

---

## Task 11: OLX Scraper

**Files:**
- Create: `src/scrapers/olx.py`

- [ ] **Step 1: Add tests**

```python
def test_olx_extract_id():
    assert olx_extract_id("https://www.olx.in/item/1-bhk-chromepet-ID1234567890.html") == "1234567890"

def test_olx_extract_id_path():
    assert olx_extract_id("https://www.olx.in/item/flat-ID9876543210.html") == "9876543210"
```

- [ ] **Step 2: Implement `src/scrapers/olx.py`**

```python
import asyncio
import logging
import re
from src.models import Listing
from src.scrapers.base import get_browser_context

logger = logging.getLogger(__name__)

SEARCH_URL = (
    "https://www.olx.in/chennai_g4058979/q-1-bhk-chromepet"
    "?filter=price_max_1500000"
)

_ID_PATTERN = re.compile(r"ID(\d+)\.html$")


def extract_id(url: str) -> str:
    match = _ID_PATTERN.search(url)
    return match.group(1) if match else url.split("/")[-1]


def parse_price(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


async def _scrape_async() -> list[Listing]:
    listings = []
    async with get_browser_context() as ctx:
        page = await ctx.new_page()
        try:
            await page.goto(SEARCH_URL, wait_until="networkidle", timeout=30000)
            cards = await page.query_selector_all("li[data-aut-id='itemBox'], [class*='_2tW1I']")
            for card in cards:
                try:
                    url_el = await card.query_selector("a")
                    if not url_el:
                        continue
                    url = await url_el.get_attribute("href")
                    if not url.startswith("http"):
                        url = "https://www.olx.in" + url
                    listing_id = extract_id(url)

                    title_el = await card.query_selector("[data-aut-id='itemTitle'], span[class*='_2poBI']")
                    title = (await title_el.inner_text()).strip() if title_el else "1 BHK"

                    price_el = await card.query_selector("[data-aut-id='itemPrice'], span[class*='_89yzn']")
                    price = parse_price(await price_el.inner_text()) if price_el else None
                    if price is None:
                        continue

                    addr_el = await card.query_selector("span[class*='tjgMj']")
                    address = (await addr_el.inner_text()).strip() if addr_el else "Chromepet, Chennai"

                    img_els = await card.query_selector_all("img[src]")
                    images = [await i.get_attribute("src") for i in img_els[:3] if await i.get_attribute("src")]

                    listings.append(Listing(
                        id=listing_id, source="olx", title=title,
                        address=address, price=price, url=url, images=images,
                    ))
                except Exception:
                    logger.exception("Error parsing OLX card")
        finally:
            await page.close()
    return listings


def scrape() -> list[Listing]:
    return asyncio.run(_scrape_async())
```

- [ ] **Step 3: Run tests and commit**

```bash
python -m pytest tests/test_scrapers.py -k "olx" -v
git add src/scrapers/olx.py tests/test_scrapers.py
git commit -m "feat: OLX scraper"
```

---

## Task 12: Housing.com Scraper

**Files:**
- Create: `src/scrapers/housing.py`

- [ ] **Step 1: Add tests**

```python
def test_housing_extract_id():
    assert hc_extract_id("https://housing.com/in/rent/properties/chennai/chromepet/abc-def-123456") == "abc-def-123456"
```

- [ ] **Step 2: Implement `src/scrapers/housing.py`**

```python
import asyncio
import logging
import re
from src.models import Listing
from src.scrapers.base import get_browser_context

logger = logging.getLogger(__name__)

SEARCH_URL = (
    "https://housing.com/in/rent/1bhk-flats-in-chromepet-chennai"
    "?f_budget_max=15000"
)


def extract_id(url: str) -> str:
    return url.rstrip("/").split("/")[-1]


def parse_price(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


async def _scrape_async() -> list[Listing]:
    listings = []
    async with get_browser_context() as ctx:
        page = await ctx.new_page()
        try:
            await page.goto(SEARCH_URL, wait_until="networkidle", timeout=30000)
            cards = await page.query_selector_all("[class*='propertyCard'], [data-testid*='card']")
            for card in cards:
                try:
                    url_el = await card.query_selector("a[href*='housing.com']")
                    if not url_el:
                        continue
                    url = await url_el.get_attribute("href")
                    if not url.startswith("http"):
                        url = "https://housing.com" + url
                    listing_id = extract_id(url)

                    title_el = await card.query_selector("h2, h3, [class*='title']")
                    title = (await title_el.inner_text()).strip() if title_el else "1 BHK"

                    price_el = await card.query_selector("[class*='price'], [class*='rent']")
                    price = parse_price(await price_el.inner_text()) if price_el else None
                    if price is None:
                        continue

                    addr_el = await card.query_selector("[class*='locality'], [class*='address']")
                    address = (await addr_el.inner_text()).strip() if addr_el else "Chromepet, Chennai"

                    img_els = await card.query_selector_all("img[src]")
                    images = [await i.get_attribute("src") for i in img_els[:3] if await i.get_attribute("src")]

                    listings.append(Listing(
                        id=listing_id, source="housing", title=title,
                        address=address, price=price, url=url, images=images,
                    ))
                except Exception:
                    logger.exception("Error parsing Housing.com card")
        finally:
            await page.close()
    return listings


def scrape() -> list[Listing]:
    return asyncio.run(_scrape_async())
```

- [ ] **Step 3: Run tests and commit**

```bash
python -m pytest tests/test_scrapers.py -k "housing" -v
git add src/scrapers/housing.py tests/test_scrapers.py
git commit -m "feat: Housing.com scraper"
```

---

## Task 13: Quikr Scraper

**Files:**
- Create: `src/scrapers/quikr.py`

- [ ] **Step 1: Add tests**

```python
def test_quikr_extract_id_numeric():
    assert qk_extract_id("https://www.quikr.com/homes/1-bhk-flat-for-rent/chromepet/12345678") == "12345678"

def test_quikr_extract_id_slug_with_numeric_suffix():
    assert qk_extract_id("https://www.quikr.com/homes/flat-for-rent-87654321") == "87654321"
```

- [ ] **Step 2: Implement `src/scrapers/quikr.py`**

```python
import asyncio
import logging
import re
from src.models import Listing
from src.scrapers.base import get_browser_context

logger = logging.getLogger(__name__)

SEARCH_URL = (
    "https://www.quikr.com/homes/1-bhk-flat-for-rent-in-chromepet-chennai"
    "?maxPrice=15000"
)

_ID_PATTERN = re.compile(r"(\d{6,})(?:/|$)")


def extract_id(url: str) -> str:
    match = _ID_PATTERN.search(url)
    return match.group(1) if match else url.rstrip("/").split("/")[-1]


def parse_price(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


async def _scrape_async() -> list[Listing]:
    listings = []
    async with get_browser_context() as ctx:
        page = await ctx.new_page()
        try:
            await page.goto(SEARCH_URL, wait_until="networkidle", timeout=30000)
            cards = await page.query_selector_all(".product-info, [class*='listing-card']")
            for card in cards:
                try:
                    url_el = await card.query_selector("a[href*='quikr.com']")
                    if not url_el:
                        continue
                    url = await url_el.get_attribute("href")
                    if not url.startswith("http"):
                        url = "https://www.quikr.com" + url
                    listing_id = extract_id(url)

                    title_el = await card.query_selector("h2, h3, .product-title")
                    title = (await title_el.inner_text()).strip() if title_el else "1 BHK"

                    price_el = await card.query_selector(".product-price, [class*='price']")
                    price = parse_price(await price_el.inner_text()) if price_el else None
                    if price is None:
                        continue

                    addr_el = await card.query_selector(".product-locality, [class*='location']")
                    address = (await addr_el.inner_text()).strip() if addr_el else "Chromepet, Chennai"

                    img_els = await card.query_selector_all("img[src]")
                    images = [await i.get_attribute("src") for i in img_els[:3] if await i.get_attribute("src")]

                    listings.append(Listing(
                        id=listing_id, source="quikr", title=title,
                        address=address, price=price, url=url, images=images,
                    ))
                except Exception:
                    logger.exception("Error parsing Quikr card")
        finally:
            await page.close()
    return listings


def scrape() -> list[Listing]:
    return asyncio.run(_scrape_async())
```

- [ ] **Step 3: Run tests and commit**

```bash
python -m pytest tests/test_scrapers.py -k "quikr" -v
git add src/scrapers/quikr.py tests/test_scrapers.py
git commit -m "feat: Quikr scraper"
```

---

## Task 14: Scheduler (Run Cycle Orchestration)

**Files:**
- Create: `src/scheduler.py`
- Create: `tests/test_scheduler.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_scheduler.py
import sqlite3
import pytest
from unittest.mock import MagicMock, patch, call
from src.db import init_db, add_pending_alert
from src.models import Listing
from src.scheduler import run_cycle


@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    yield conn
    conn.close()


def make_listing(**kwargs):
    defaults = dict(id="1", source="nobroker", title="1 BHK in Chromepet",
                    address="Chromepet", price=12000, url="https://nobroker.in/1")
    return Listing(**{**defaults, **kwargs})


def test_run_cycle_sends_new_listing(db_conn):
    listing = make_listing()
    with (
        patch("src.scheduler.run_all_scrapers", return_value=[listing]),
        patch("src.scheduler.apply_property_filter", return_value=[listing]),
        patch("src.scheduler.apply_distance_filter", return_value=[(listing, "PREFERRED", 3.2)]),
        patch("src.scheduler.send_alert", return_value="SMtest"),
        patch("src.scheduler.mark_seen") as mock_mark,
    ):
        run_cycle(db_conn, office_lat=12.97, office_lng=80.14)
        mock_mark.assert_called_once_with(db_conn, "1", "nobroker")


def test_run_cycle_skips_seen_listing(db_conn):
    from src.db import mark_seen
    mark_seen(db_conn, "1", "nobroker")
    listing = make_listing()
    with (
        patch("src.scheduler.run_all_scrapers", return_value=[listing]),
        patch("src.scheduler.apply_property_filter", return_value=[listing]),
        patch("src.scheduler.apply_distance_filter", return_value=[(listing, "PREFERRED", 3.2)]),
        patch("src.scheduler.send_alert") as mock_send,
    ):
        run_cycle(db_conn, office_lat=12.97, office_lng=80.14)
        mock_send.assert_not_called()


def test_run_cycle_queues_on_twilio_failure(db_conn):
    listing = make_listing()
    with (
        patch("src.scheduler.run_all_scrapers", return_value=[listing]),
        patch("src.scheduler.apply_property_filter", return_value=[listing]),
        patch("src.scheduler.apply_distance_filter", return_value=[(listing, "PREFERRED", 3.2)]),
        patch("src.scheduler.send_alert", side_effect=Exception("Twilio down")),
        patch("src.scheduler.add_pending_alert") as mock_queue,
    ):
        run_cycle(db_conn, office_lat=12.97, office_lng=80.14)
        mock_queue.assert_called_once()


def test_run_cycle_retries_pending_alerts(db_conn):
    listing = make_listing(id="pending1")
    add_pending_alert(db_conn, listing, "PREFERRED", 3.0)

    with (
        patch("src.scheduler.run_all_scrapers", return_value=[]),
        patch("src.scheduler.apply_property_filter", return_value=[]),
        patch("src.scheduler.apply_distance_filter", return_value=[]),
        patch("src.scheduler.send_alert", return_value="SMretried"),
        patch("src.scheduler.resolve_pending_alert") as mock_resolve,
    ):
        run_cycle(db_conn, office_lat=12.97, office_lng=80.14)
        mock_resolve.assert_called_once()
```

- [ ] **Step 2: Run to verify they fail**

```bash
python -m pytest tests/test_scheduler.py -v
```

- [ ] **Step 3: Implement `src/scheduler.py`**

```python
import logging
import sqlite3
from src.db import (
    is_seen, mark_seen, add_pending_alert,
    get_pending_alerts, resolve_pending_alert,
    increment_retry, delete_stale_pending,
)
from src.filters.property_filter import passes_property_filter
from src.filters.distance_filter import apply_distance_filter
from src.models import Listing
from src.notifier.whatsapp import send_alert

logger = logging.getLogger(__name__)

SCRAPERS = [
    "src.scrapers.nobroker",
    "src.scrapers.magicbricks",
    "src.scrapers.acres99",
    "src.scrapers.olx",
    "src.scrapers.housing",
    "src.scrapers.quikr",
]


def run_all_scrapers() -> list[Listing]:
    import importlib
    all_listings = []
    for module_path in SCRAPERS:
        try:
            module = importlib.import_module(module_path)
            results = module.scrape()
            logger.info("Scraped %d listings from %s", len(results), module_path)
            all_listings.extend(results)
        except Exception:
            logger.exception("Scraper failed: %s", module_path)
    return all_listings


def apply_property_filter(listings: list[Listing]) -> list[Listing]:
    return [l for l in listings if passes_property_filter(l)]


def run_cycle(conn: sqlite3.Connection, office_lat: float, office_lng: float) -> None:
    logger.info("Starting run cycle")

    # Step 1: Retry pending alerts
    delete_stale_pending(conn, max_retries=48)
    for row_id, listing, zone, distance_km in get_pending_alerts(conn):
        try:
            sid = send_alert(listing, zone, distance_km)
            resolve_pending_alert(conn, row_id)
            mark_seen(conn, listing.id, listing.source)
            logger.info("Retried pending alert %d → SID %s", row_id, sid)
        except Exception:
            increment_retry(conn, row_id)
            logger.warning("Pending alert %d retry failed", row_id)

    # Step 2: Scrape
    raw = run_all_scrapers()
    filtered = apply_property_filter(raw)
    logger.info("%d listings after property filter", len(filtered))

    # Step 3: Distance filter
    candidates = apply_distance_filter(filtered, conn, office_lat, office_lng)
    logger.info("%d listings after distance filter", len(candidates))

    # Step 4: Dedup + alert
    for listing, zone, distance_km in candidates:
        if is_seen(conn, listing.id, listing.source):
            continue
        try:
            sid = send_alert(listing, zone, distance_km)
            mark_seen(conn, listing.id, listing.source)
            logger.info("Alerted listing %s/%s (SID: %s)", listing.source, listing.id, sid)
        except Exception:
            logger.exception("Failed to send alert for %s/%s — queuing", listing.source, listing.id)
            add_pending_alert(conn, listing, zone, distance_km)

    logger.info("Run cycle complete")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_scheduler.py -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add src/scheduler.py tests/test_scheduler.py
git commit -m "feat: run cycle orchestration with retry, dedup, filter, and alert"
```

---

## Task 15: Main Entrypoint

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Implement `main.py`**

```python
import logging
import os
import sqlite3
from dotenv import load_dotenv
from apscheduler.schedulers.blocking import BlockingScheduler
from src.db import init_db, get_connection
from src.notifier.whatsapp import health_check
from src.scheduler import run_cycle

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("DB_PATH", "/app/data/rental_monitor.db")
OFFICE_LAT = float(os.environ.get("OFFICE_LAT", "12.9698"))
OFFICE_LNG = float(os.environ.get("OFFICE_LNG", "80.1409"))


def main():
    conn = get_connection(DB_PATH)
    init_db(conn)

    logger.info("Running startup WhatsApp health-check...")
    ok = health_check()
    if not ok:
        logger.warning(
            "Startup health-check FAILED. Twilio sandbox may have expired. "
            "Re-send the join message from your phone, then restart the container. "
            "Skipping first scrape cycle — will retry in 1 hour."
        )

    scheduler = BlockingScheduler()
    scheduler.add_job(
        func=lambda: run_cycle(conn, OFFICE_LAT, OFFICE_LNG),
        trigger="interval",
        hours=1,
        max_instances=1,
        id="rental_monitor",
        name="Rental Monitor Hourly Run",
    )

    if ok:
        logger.info("Running first cycle immediately...")
        run_cycle(conn, OFFICE_LAT, OFFICE_LNG)

    logger.info("Scheduler started. Checking every hour.")
    scheduler.start()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add main.py
git commit -m "feat: main entrypoint with health-check and APScheduler"
```

---

## Task 16: Docker Build & End-to-End Smoke Test

- [ ] **Step 1: Run all unit tests and confirm full pass**

```bash
python -m pytest tests/ -v
```

Expected: all tests pass. Fix any failures before proceeding.

- [ ] **Step 2: Copy `.env.example` to `.env` and fill in your Twilio credentials**

```bash
cp .env.example .env
# Edit .env with your actual TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN
```

- [ ] **Step 3: Build Docker image**

```bash
docker-compose build
```

Expected: build completes with no errors, Playwright Chromium installed.

- [ ] **Step 4: Start the container**

```bash
docker-compose up
```

Expected log output:
```
Running startup WhatsApp health-check...
Health check passed. SID: SMxxxxxxxx
Running first cycle immediately...
Starting run cycle
Scraped N listings from src.scrapers.nobroker
...
Run cycle complete
Scheduler started. Checking every hour.
```

- [ ] **Step 5: Confirm WhatsApp test message received on 8610385533**

Check your phone. You should see:
```
🏠 Rental Monitor is active and watching for listings. (startup check)
```

If not received, check the container logs for the Sandbox expiry warning and re-send the join message.

- [ ] **Step 6: Verify first real alert (if listings exist)**

Wait a few minutes after the first cycle. If matching listings are found, you should receive a WhatsApp message in the format defined in the spec.

- [ ] **Step 7: Confirm container restarts cleanly**

```bash
docker-compose restart
```

Expected: health-check message received again on your phone within ~30 seconds.

- [ ] **Step 8: Final commit**

```bash
git add .
git commit -m "chore: verified Docker build and end-to-end WhatsApp delivery"
```

---

## Full Test Run Reference

```bash
# Run all tests at any time
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_distance_filter.py -v

# Run tests matching a keyword
python -m pytest tests/ -k "nobroker" -v
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| WhatsApp health-check fails on startup | Re-send Sandbox join message from your phone |
| Scraper returns 0 results | Site may have changed selectors — check logs, update CSS selectors in the relevant scraper |
| Geocoding returns None for all addresses | Check Nominatim rate-limit / IP block — add `time.sleep(1)` if missing |
| Docker container keeps restarting | Check logs: `docker-compose logs --tail=50` |
| `playwright install` fails in Docker | Ensure `--with-deps` flag is in Dockerfile RUN command |
