# Rental Monitor

Automatically scrapes rental listings across Chennai (or any Indian city), filters by your budget and commute time, and sends new matches to Telegram. Dedups across portals so the same flat never alerts twice.

## What it does

- Async scrape of Sulekha, SquareYards, 99acres, MagicBricks, OLX, DuckDuckGo every hour
- Filters by property type, price range, and distance from your office (haversine)
- Dedups across sources via geohash + price-bucket fingerprint
- Per-cycle ranking by `fit_score` (commute, price, locality, freshness, confirmations)
- Per-source circuit breaker + token-bucket politeness; one source crashing never aborts the cycle
- Pending-alerts retry queue + automatic prune of stale rows
- Daily Telegram digest (top-5 + per-source health + silent-source detector)

## Setup

**1. Clone and install**
```bash
git clone https://github.com/harshadhanishsr/rental-monitor
cd rental-monitor
uv sync
```

**2. Create your `.env` file**
```bash
cp .env.example .env
```
Fill in:
```
TELEGRAM_BOT_TOKEN=...       # From @BotFather on Telegram (free)
TELEGRAM_CHAT_ID=...         # Your chat ID
OFFICE_LAT=13.0827           # Your office coordinates
OFFICE_LNG=80.2707
# Optional:
PROXY_URL=                   # Set to bypass regional blocks (httpx-compatible URL)
LLM_API_KEY=                 # Reserved for the v2.1 LLM enrichment layer (no-op when blank)
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

One-shot (cron, CI):
```bash
uv run python run_once.py
```

Long-running loop:
```bash
uv run python monitor.py
```

Daily digest (top-5 + source health):
```bash
uv run python run_once.py --digest
```

## Cutover from v1

If you're upgrading from the v1 schema (`seen_listings`), seed the v2 DB so old items don't re-alert under the new fingerprint:

```bash
uv run python scripts/seed_v2_seen.py legacy.db data/rental_monitor.db
```

Old v1 modules live under `legacy/` for the rollout window and are scheduled for deletion (Task 6.1).

## Project structure

```
rental-monitor/
├── monitor.py              # long-running loop wrapper around run_once.main()
├── run_once.py             # single cycle (used by hourly + digest workflows)
├── config.py               # user-facing settings (city/budget/radius/...)
├── pyproject.toml          # uv-managed deps
├── src/
│   ├── core/               # AsyncHttp, TokenBucket, Breaker, run_cycle engine
│   ├── sources/            # SourceAdapter ABC + per-portal adapters + registry
│   ├── pipeline/           # filter, dedup, rank, enrich, prune, digest
│   ├── notifier/           # telegram sender, alert_v2 wrapper, digest
│   ├── state/              # aiosqlite connect + migrations
│   └── models.py           # pydantic Listing + RunStats
├── scripts/                # refresh_fixtures.py, seed_v2_seen.py
├── tests/                  # adapter + pipeline + unit tests + HTML fixtures
└── legacy/                 # v1 modules quarantined until removal (Task 6.1)
```

## CI workflows

- `.github/workflows/monitor.yml` — hourly cycle (`run_once.py`)
- `.github/workflows/digest.yml`  — daily digest at 09:00 IST

Both restore `data/rental_monitor.db` from the `state` branch before running and write back on completion. **Don't push to the `state` branch by hand** — it's managed by the workflows and force-overwriting it will corrupt the live DB.

## Getting API keys (free, no credit card)

| Service          | Link                       | Use                |
|------------------|----------------------------|--------------------|
| Telegram Bot     | Search @BotFather, /newbot | Notifications      |
| Ola Maps         | maps.olacabs.com           | (Future) commute   |
| OpenRouteService | openrouteservice.org       | (Future) walking   |

`OLA_MAPS_API_KEY` and `ORS_API_KEY` are no-ops in v2.0.0 (the heuristic commute is used). Plumbed env vars stay for the v2.1 commute integration.

## Tests

```bash
uv run pytest -q
```

All adapter tests run against checked-in HTML fixtures so no network calls fire in CI.
