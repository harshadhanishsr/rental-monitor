# Rental Space Monitor — Design Spec

**Date:** 2026-03-22
**Project:** rental-monitor
**Status:** Approved

---

## Goal

Continuously monitor rental listing platforms for 1 BHK apartments in and around Chromepet / Mimillichery, Chennai. Alert the user via WhatsApp when a matching listing is found — including images, reviews, distance from office, and a direct link.

---

## Requirements

### Property Filters
- Type: 1 BHK
- Furnishing: Any (furnished, semi-furnished, unfurnished)
- Max rent: ₹15,000/month
- Occupancy: Bachelor-friendly (explicit filter where available; keyword match elsewhere)

### Location & Distance
- Office anchor: Ishwarya Nagar, Mimillichery, Chromepet (Blackstraw AI)
  - Coordinates: ~12.9698° N, 80.1409° E
- Distance zones:
  - ≤ 5km → **PREFERRED** — always alert
  - 5–10km → **ACCEPTABLE** — always alert
  - > 10km → **FAR BUT WORTH IT** — alert only if price ≤ ₹10,000 AND rating ≥ 4.0 stars

### Check Frequency
- Every hour via APScheduler

---

## Data Sources

| Source | Method |
|---|---|
| NoBroker | Playwright (JS-rendered) |
| MagicBricks | Playwright |
| 99acres | Playwright |
| OLX | Playwright |
| Housing.com | Playwright |
| Quikr | Playwright |
| X (Twitter) | Playwright / ntscraper (keyword search) |

Search keywords for X and unstructured sources:
- "1bhk chromepet rent", "1bhk mimillichery rent", "1 bhk for rent chromepet", "bachelor 1bhk chromepet"

---

## Architecture

```
Docker Container (auto-restart)
│
├── APScheduler — triggers every 60 minutes
│
├── Scraper Engine
│   ├── nobroker.py
│   ├── magicbricks.py
│   ├── 99acres.py
│   ├── olx.py
│   ├── housing.py
│   ├── quikr.py
│   └── twitter.py
│
├── Filter Engine
│   ├── property_filter.py  — 1BHK, ≤15K, bachelor-friendly
│   └── distance_filter.py  — geocode + haversine from office
│
├── Dedup Store
│   └── SQLite (seen_listings.db) — listing ID + source + first seen timestamp
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
- `id` (str) — unique identifier from source
- `source` (str) — platform name
- `title` (str)
- `address` (str)
- `price` (int) — monthly rent in INR
- `furnishing` (str) — furnished / semi-furnished / unfurnished / unknown
- `bachelors_allowed` (bool | None)
- `rating` (float | None) — platform rating if available
- `review_snippet` (str | None) — top review text
- `images` (list[str]) — up to 3 image URLs
- `url` (str) — direct listing link
- `lat` (float | None) — geocoded latitude
- `lng` (float | None) — geocoded longitude

### Filter Engine
1. **Property filter:** price ≤ 15000, type contains "1bhk"/"1 bhk", bachelors_allowed is True or None (unknown)
2. **Distance filter:**
   - Geocode address using Nominatim (OpenStreetMap, free, no API key)
   - Calculate distance using Haversine formula
   - Apply zone logic (see Requirements)

### Dedup Store
- SQLite table: `seen_listings(id TEXT, source TEXT, seen_at TEXT)`
- Before alerting, check if `(id, source)` already exists
- Insert after alerting — never alert for the same listing twice

### Notifier
- Twilio WhatsApp API
- Sends text message + up to 3 image media attachments
- Message format (see below)

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

Images sent as separate Twilio media message attachments (up to 3).

---

## Tech Stack

| Component | Library/Tool |
|---|---|
| Language | Python 3.11 |
| Browser automation | Playwright |
| Scheduling | APScheduler |
| Geocoding | geopy (Nominatim) |
| Distance | haversine |
| Dedup store | SQLite (stdlib) |
| WhatsApp | Twilio Python SDK |
| Container | Docker + docker-compose |

---

## Setup Steps (First Run)

1. Clone repo and copy `.env.example` to `.env`
2. Create Twilio account → enable WhatsApp Sandbox → add number 8610385533
3. Fill `.env` with `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`, `WHATSAPP_TO`
4. `docker-compose up --build`
5. Verify test WhatsApp message is received before scrapers run

---

## Error Handling

- Each scraper runs independently — one failure does not stop others
- Failed scrapes are logged with stack trace; scheduler retries next hour
- Geocoding failures: listing is alerted without distance info, flagged as "Distance unknown"
- Twilio failures: logged, alert queued for next run attempt

---

## Out of Scope

- Web dashboard / UI
- Multiple users / shared alerts
- Automatic booking or contacting landlords
- Storing full listing details beyond dedup (only IDs stored)
