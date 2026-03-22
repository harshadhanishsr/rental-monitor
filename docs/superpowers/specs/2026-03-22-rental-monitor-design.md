# Rental Space Monitor — Design Spec

**Date:** 2026-03-22
**Project:** rental-monitor
**Status:** Approved

---

## Goal

Continuously monitor rental listing platforms for 1 BHK apartments in and around Chromepet / Mimillichery, Chennai. Alert the user via WhatsApp when a matching listing is found — including a direct link, reviews, distance from office, and price.

---

## Requirements

### Property Filters
- Type: 1 BHK
- Furnishing: Any (furnished, semi-furnished, unfurnished)
- Max rent: ₹15,000/month
- Occupancy: Bachelor-friendly
  - Where platform exposes this filter, apply it directly
  - Where not exposed, keyword-match listing title/description for "bachelor" / "single"
  - If `bachelors_allowed` is unknown (None), treat as allowed — to avoid missing valid listings. Listings explicitly marked "families only" (`bachelors_allowed = False`) are excluded.

### Location & Distance
- Office anchor defined via environment variables (`OFFICE_LAT`, `OFFICE_LNG`)
  - Default: Ishwarya Nagar, Mimillichery, Chromepet (~12.9698° N, 80.1409° E)
- Distance zones:
  - ≤ 5km → **PREFERRED** — always alert
  - 5–10km → **ACCEPTABLE** — always alert
  - > 10km → **FAR BUT WORTH IT** — alert only if price ≤ ₹10,000 AND rating ≥ 4.0 stars
    - If rating is None in the FAR zone, skip the listing (do not alert) — avoids noise from unrated low-quality listings

### Check Frequency
- Every hour via APScheduler with `max_instances=1` to prevent overlapping runs

---

## Data Sources (v1)

| Source | Method |
|---|---|
| NoBroker | Playwright (JS-rendered) |
| MagicBricks | Playwright |
| 99acres | Playwright |
| OLX | Playwright |
| Housing.com | Playwright |
| Quikr | Playwright |

**X (Twitter) — excluded from v1.** X aggressively blocks headless browsers in 2026, and unstructured posts rarely contain structured price/location data needed for reliable filtering. Will be revisited in v2 if a paid API tier is available.

---

## Architecture

```
Docker Container (restart: always)
│
├── APScheduler — triggers every 60 minutes (max_instances=1)
│
├── Scraper Engine
│   ├── nobroker.py
│   ├── magicbricks.py
│   ├── 99acres.py
│   ├── olx.py
│   ├── housing.py
│   └── quikr.py
│
├── Filter Engine
│   ├── property_filter.py  — 1BHK, ≤15K, bachelor-friendly
│   └── distance_filter.py  — geocode + haversine from office
│
├── SQLite Database (data/rental_monitor.db)
│   ├── seen_listings      — dedup store
│   ├── geocode_cache      — address → lat/lng cache
│   └── pending_alerts     — alerts queued on Twilio failure
│
└── Notifier
    └── whatsapp.py — Twilio WhatsApp API
```

---

## Components

### Scraper Modules

Each module implements a common interface:
```python
def scrape() -> list[Listing]
```

`Listing` dataclass fields:
- `id` (str) — unique identifier from source (see per-scraper extraction below)
- `source` (str) — platform name
- `title` (str)
- `address` (str)
- `price` (int) — monthly rent in INR
- `furnishing` (str) — furnished / semi-furnished / unfurnished / unknown
- `bachelors_allowed` (bool | None)
- `rating` (float | None) — platform rating if available
- `review_snippet` (str | None) — top review text (1–2 sentences)
- `images` (list[str]) — up to 3 image URLs (scraped; best-effort, may be empty)
- `url` (str) — direct listing link
- `lat` (float | None) — populated by distance filter, not by scraper
- `lng` (float | None) — populated by distance filter, not by scraper

**Per-scraper ID extraction:**
- NoBroker: last path segment of URL, e.g. `/property/12345678` → `12345678`
- MagicBricks: `propertyId` query param or path segment
- 99acres: numeric ID from URL path
- OLX: numeric listing ID from URL
- Housing.com: property ID from URL path
- Quikr: numeric listing ID from URL (session-based URLs are normalized to ID before storage)

Cross-platform duplicates (same property listed on two platforms) will trigger two separate alerts. This is a known and accepted behavior given the `(id, source)` composite dedup key.

### Filter Engine

1. **Property filter:** price ≤ 15000, type contains "1bhk" / "1 bhk", `bachelors_allowed` is not False
2. **Distance filter:**
   - Look up `address_hash` in `geocode_cache` first
   - On cache miss: geocode using Nominatim (OpenStreetMap) with a 1-second delay between requests; set User-Agent to `rental-monitor/1.0` as required by Nominatim's usage policy
   - Cache result in `geocode_cache` for all future runs. Cache entries have no TTL in v1 — they persist indefinitely. Manual invalidation (`DELETE FROM geocode_cache`) is the supported mechanism if coordinates appear incorrect.
   - On geocoding failure: alert without distance, label "Distance unknown"
   - Calculate distance using Haversine formula
   - Apply zone logic (see Requirements)

### SQLite Schema

```sql
CREATE TABLE seen_listings (
    id TEXT NOT NULL,
    source TEXT NOT NULL,
    seen_at TEXT NOT NULL,
    PRIMARY KEY (id, source)
);

CREATE TABLE geocode_cache (
    address_hash TEXT PRIMARY KEY,  -- SHA256 of normalized address string
    lat REAL NOT NULL,
    lng REAL NOT NULL,
    cached_at TEXT NOT NULL
);

CREATE TABLE pending_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id TEXT NOT NULL,
    source TEXT NOT NULL,
    payload_json TEXT NOT NULL,     -- full serialized Listing
    created_at TEXT NOT NULL,
    retry_count INTEGER DEFAULT 0
);
```

### Dedup & Alert Flow

1. Filter engine produces a list of matching `Listing` objects
2. For each listing, check `seen_listings` for `(id, source)` — skip if found
3. Attempt Twilio send
4. **Only on confirmed send** (Twilio returns a message SID without exception): insert into `seen_listings`
5. On Twilio failure: insert into `pending_alerts` (not into `seen_listings`)
6. At start of each hourly run, retry all rows in `pending_alerts` before running scrapers
7. Remove from `pending_alerts` after confirmed successful retry
8. If `retry_count` reaches 48 (≈48 hours of retries): delete the row and log a warning — the listing is considered stale. On sandbox session re-join after extended downtime, only pending alerts created within the last 48 hours are delivered, avoiding a flood of outdated listings.

### Notifier

- Twilio WhatsApp API via Python SDK
- Sends one text message per listing
- Images: up to 3 image URLs from `listing.images` sent as Twilio media attachments (best-effort)
  - Note: some CDN image URLs from rental platforms may be signed or require session cookies, causing Twilio's fetch to fail. If media attachment fails, the text message is still sent. This is a known v1 limitation.
- **Twilio Sandbox limitation:** The WhatsApp Sandbox requires the recipient to send a join message to the sandbox number every 72 hours. A startup health-check sends a test message on container start. If delivery fails, the container logs a clear warning and **skips the current scrape cycle** (does not exit). The scraper will retry the health-check on the next hourly tick. This avoids a Docker restart loop (`restart: always` is used for crash recovery, not sandbox session issues).

---

## WhatsApp Alert Format

```
NEW 1BHK — PREFERRED (3.2km from office)

📍 Chromepet Main Road, Mimillichery
💰 ₹12,500/month | Semi-furnished
✅ Bachelors allowed | No broker
⭐ 4.3/5 — "Clean, good water supply, responsive owner"
🌐 Source: NoBroker
🔗 https://nobroker.in/...

Found at: 14:03, 22 Mar 2026
```

If distance is unknown: replace zone header with `NEW 1BHK — Distance unknown`.
If rating is unavailable: omit the ⭐ line.

---

## Environment Variables (`.env`)

```
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886   # Twilio Sandbox number
WHATSAPP_TO=whatsapp:+918610385533
OFFICE_LAT=12.9698
OFFICE_LNG=80.1409
```

---

## Tech Stack

| Component | Library/Tool |
|---|---|
| Language | Python 3.11 |
| Browser automation | Playwright |
| Scheduling | APScheduler |
| Geocoding | geopy (Nominatim) |
| Distance | haversine |
| Database | SQLite (stdlib) |
| WhatsApp | Twilio Python SDK |
| Container | Docker + docker-compose |

---

## Setup Steps (First Run)

1. Clone repo, copy `.env.example` to `.env`, fill in values
2. Create Twilio account → navigate to Messaging → Try it out → Send a WhatsApp message
3. From your phone (8610385533), send the sandbox join message to activate the session
4. Fill in Twilio credentials in `.env`
5. `docker-compose up --build`
6. Container sends a startup health-check WhatsApp message — confirm receipt before first scrape runs
7. **Note:** Twilio Sandbox sessions expire every 72 hours. You must re-send the join message from your phone to renew. The container will log a warning if the session has expired.

---

## Error Handling

- Each scraper runs independently — one failure does not stop others
- Failed scrapes are logged with stack trace; scheduler retries next hour
- Geocoding failures: listing is alerted without distance info, flagged as "Distance unknown"
- Twilio failures: listing inserted into `pending_alerts`, retried on next run (never silently dropped)
- APScheduler: `max_instances=1` — if a run takes > 60 min, the next scheduled run is skipped

---

## Out of Scope (v1)

- X (Twitter) and social media scraping — revisit in v2
- Web dashboard / UI
- Multiple users / shared alerts
- Automatic booking or contacting landlords
- Storing full listing details beyond dedup (only IDs and pending alerts stored)
- Image re-hosting (Twilio image delivery is best-effort)
