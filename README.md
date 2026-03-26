# Rental Monitor

Automatically scrapes Indian rental portals for 1 BHK / 2 BHK / 1 RK listings matching your budget and location, then sends alerts to **Telegram** (or WhatsApp) whenever a new match appears.

Built for Chennai but **fully configurable** for any Indian city.

---

## Features

- Scrapes **NoBroker, 99acres, Sulekha, OLX, MagicBricks, Housing.com** (+ DuckDuckGo meta-search as fallback)
- Filters by price, distance from your office/workplace, and property type
- Sends instant **Telegram** alerts with Google Maps links
- Deduplicates listings — you only get alerted once per property
- Runs on a schedule (default: every hour)
- **One config file** (`config.py`) to set everything: city, areas, budget, radius, property type

---

## Quick Start

### 1. Clone & install

```bash
git clone https://github.com/YOUR_USERNAME/rental-monitor.git
cd rental-monitor

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium     # only needed for 99acres scraper
```

### 2. Configure your search

Edit **`config.py`** — this is the only file you need to change:

```python
# Where is your office / reference point?
OFFICE_LAT = 12.9698
OFFICE_LNG = 80.1409

CITY         = "Chennai"
SEARCH_AREAS = ["Chromepet", "Pallavaram", "Tambaram", "Nanganallur"]

MAX_RADIUS_KM = 10.0    # only show listings within 10 km
MAX_RENT      = 15_000  # ₹/month budget
PROPERTY_TYPE = "1bhk"  # "1rk" | "1bhk" | "2bhk" | "3bhk"
NUM_PEOPLE    = 1       # 1 = bachelor, 2+ = family
```

### 3. Set up notifications

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

**Telegram (free, recommended):**
1. Message [@BotFather](https://t.me/BotFather) → `/newbot` → copy the token
2. Send any message to your new bot
3. Visit `https://api.telegram.org/bot<TOKEN>/getUpdates` → copy the `chat.id`
4. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`

Test it:
```bash
python setup_telegram.py
```

### 4. Run

**One-shot search (print + send results now):**
```bash
python fetch_now.py
```

**Background monitor (checks every hour):**
```bash
python main.py
```

---

## Config Reference (`config.py`)

| Setting | Default | Description |
|---|---|---|
| `OFFICE_LAT` / `OFFICE_LNG` | Chromepet, Chennai | Your workplace / reference point |
| `CITY` | `"Chennai"` | City to search |
| `SEARCH_AREAS` | `["Chromepet", ...]` | Localities to actively search |
| `PRIORITY_LOCALITIES` | *(see file)* | Areas shown first in alerts |
| `MAX_RADIUS_KM` | `10.0` | Max distance from office (km) |
| `MAX_RENT` | `15000` | Max monthly rent (₹) |
| `MIN_RENT` | `3000` | Min monthly rent (₹) |
| `PROPERTY_TYPE` | `"1bhk"` | `"1rk"` / `"1bhk"` / `"2bhk"` / `"3bhk"` |
| `NUM_PEOPLE` | `1` | 1 = solo / bachelor, 2+ = family |
| `FURNISHING` | `"any"` | `"any"` / `"furnished"` / `"semi-furnished"` / `"unfurnished"` |
| `CHECK_INTERVAL_SECONDS` | `3600` | How often the scheduler runs |

---

## Using for a Different City

1. Change `CITY`, `OFFICE_LAT`, `OFFICE_LNG`, `SEARCH_AREAS`, and `PRIORITY_LOCALITIES` in `config.py`
2. The scrapers automatically build their search URLs from these values
3. Update the geocoder bounding box in `src/filters/distance_filter.py` if your city falls outside the default Chennai lat/lng range

---

## Project Structure

```
rental-monitor/
├── config.py                  ← Edit this to customise your search
├── fetch_now.py               ← One-shot search + alert
├── main.py                    ← Background scheduler
├── requirements.txt
├── .env.example               ← Copy to .env and fill in credentials
├── src/
│   ├── scrapers/
│   │   ├── nobroker.py        ← NoBroker scraper
│   │   ├── acres99.py         ← 99acres scraper (Playwright)
│   │   ├── sulekha.py         ← Sulekha JSON-LD scraper
│   │   ├── olx.py             ← OLX scraper
│   │   ├── magicbricks.py     ← MagicBricks scraper
│   │   ├── housing.py         ← Housing.com scraper
│   │   ├── quikr.py           ← Quikr scraper
│   │   └── duckduckgo.py      ← DDG meta-search (bot-blocking bypass)
│   ├── filters/
│   │   ├── property_filter.py ← Budget, type, bachelor/family filter
│   │   └── distance_filter.py ← Geocoding + distance zones
│   ├── notifier/
│   │   ├── telegram_bot.py    ← Telegram alerts
│   │   └── whatsapp.py        ← WhatsApp via Twilio (fallback)
│   ├── scheduler.py           ← Orchestrates scrape → filter → alert
│   ├── db.py                  ← SQLite deduplication + geocode cache
│   └── models.py              ← Listing dataclass
└── tests/
```

---

## Alert Format

Each Telegram alert looks like:

```
🏠 [SUPER CLOSE] 1.4km ⭐ PRIORITY AREA
1 BHK Apartment for Rent in Chromepet
📍 Chromepet, Chennai
💰 ₹12,000/month | Semi-Furnished
🌐 nobroker.in
🔗 https://www.nobroker.in/property/...
🗺 https://maps.google.com/?q=12.957,80.143
```

---

## How the Scrapers Work

| Scraper | Method | Bot-blocking risk |
|---|---|---|
| **99acres** | Playwright (headless browser) | Low |
| **Sulekha** | JSON-LD extraction via curl_cffi | Low |
| **DuckDuckGo** | HTML search via curl_cffi (meta-search) | Low |
| **NoBroker** | Next.js `__NEXT_DATA__` JSON | High — usually blocked |
| **OLX** | `__PRELOADED_STATE__` JSON | High — often times out |
| **MagicBricks** | API + HTML | High — 403/blocked |
| **Housing.com** | Next.js JSON | High — 406 |

> The DuckDuckGo scraper bypasses portal bot-blocking by searching DDG for individual listing pages (e.g., `site:nobroker.in`) and extracting prices from the URLs/snippets.

---

## Requirements

- Python 3.11+
- `curl_cffi` (Chrome TLS fingerprint impersonation — avoids bot detection)
- Playwright (for 99acres)
- Telegram bot token (free) or Twilio account (for WhatsApp)

---

## License

MIT
