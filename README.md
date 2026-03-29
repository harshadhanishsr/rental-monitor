# Rental Monitor

Automatically scrapes rental listings across Chennai (or any Indian city), filters by your budget and commute time, and sends new matches to Telegram. Never shows the same listing twice.

## What it does

- Scrapes 99acres, Sulekha, NoBroker, MagicBricks, OLX, Housing.com every hour
- Filters by property type, price range, and distance from your office
- Gets real transit commute time using Ola Maps + OpenRouteService
- Sends only new listings to Telegram — no repeats across restarts

## Setup

**1. Clone and install**
```bash
git clone https://github.com/harshadhanishsr/rental-monitor
cd rental-monitor
pip install -r requirements.txt
```

**2. Create your `.env` file**
```bash
cp .env.example .env
```
Fill in:
```
TELEGRAM_BOT_TOKEN=...       # From @BotFather on Telegram (free)
TELEGRAM_CHAT_ID=...         # Your chat ID
OLA_MAPS_API_KEY=...         # Free at maps.olacabs.com
ORS_API_KEY=...              # Free at openrouteservice.org
OFFICE_LAT=13.0827           # Your office coordinates
OFFICE_LNG=80.2707
```

**3. Configure your search** — edit `config.py`:
```python
CITY = "Chennai"
SEARCH_AREAS = ["Pallikaranai", "Velachery", ...]   # Areas to search
MAX_RADIUS_KM = 12.0                                 # Max distance from office
PROPERTY_TYPE = "1bhk"                               # 1bhk / 2bhk / 1rk
MIN_RENT = 3000                                      # Budget range (Rs/month)
MAX_RENT = 15000
```

**4. Run**
```bash
python monitor.py
```

Scans every hour. Each Telegram alert shows address, price, furnishing, and real transit time to your office (green <20 min / yellow <40 min / red >40 min).

## Getting API keys (both free, no credit card)

| Service | Link | Use |
|---------|------|-----|
| Telegram Bot | Search @BotFather, send /newbot | Notifications |
| Ola Maps | maps.olacabs.com | Driving/transit times |
| OpenRouteService | openrouteservice.org | Walking time |

## Project structure

```
rental-monitor/
├── monitor.py          # Main entry point — run this
├── config.py           # All settings (edit this to customise)
├── requirements.txt
├── .env.example        # Copy to .env and fill in your keys
└── src/
    ├── scrapers/       # One file per property portal
    ├── filters/        # Distance + property type filters
    ├── notifier/       # Telegram alerts
    ├── travel_time.py  # Ola Maps + ORS commute calculator
    ├── db.py           # SQLite (seen listings, travel cache)
    ├── models.py       # Listing dataclass
    └── scheduler.py    # Scraper runner
```
