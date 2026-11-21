# Rental Monitor

Get Telegram alerts the moment new rentals show up in your area. Set it up once with a 2-minute wizard — it runs on GitHub's servers forever, even when your laptop is off.

## What it does

- Every hour, scans 6 rental sites (Sulekha, SquareYards, 99acres, MagicBricks, OLX, DuckDuckGo) for listings in your area
- Filters by city, area, distance, bedrooms, budget, and furnishing
- Skips duplicates — if the same flat is on 3 sites, you get one alert (not three)
- Ranks by best fit: closer + cheaper + confirmed on multiple sites = higher score
- Sends each match to Telegram with price, address, and a link
- Every morning at 9:00 IST you get a digest of the top picks from the last 24h

## What an alert looks like

```
🏠 1 BHK — Pallavaram, Chennai
₹12,500/month  ·  Sulekha
1.2 km from your location  ·  furnished
https://property.sulekha.com/...
```

If multiple sites carry the same flat, the alert says "seen on 3" and you only get pinged once.

## Setup — 3 steps, ~5 minutes

You need: a Telegram account, a GitHub account, Python 3.11+, and [uv](https://docs.astral.sh/uv/) (install in one line — see uv's site).

### Step 1 — Get the repo on your GitHub

If you're not the original owner, **fork it** first (button at top-right of GitHub), then clone your fork:

```bash
git clone https://github.com/<your-username>/rental-monitor
cd rental-monitor
uv sync
```

### Step 2 — Get your Telegram bot token

1. Open Telegram → search **@BotFather**
2. Send `/newbot` → pick a name → pick a username ending in `bot`
3. BotFather replies with a token like `123456:ABC-DEF...` — **save it**
4. Open your new bot in Telegram and send it any message (`hi` works)
5. In your browser, open `https://api.telegram.org/bot<TOKEN>/getUpdates` (paste your real token in place of `<TOKEN>`)
6. Find `"chat":{"id":12345678}` in the page — **that number is your chat ID**

### Step 3 — Run the wizard

```bash
uv run python configure.py
```

It asks 11 plain questions:

| Question | Example answer |
|---|---|
| Which city? | `Chennai` |
| Main neighbourhood? | `Pallavaram` |
| Other nearby areas to also search? | `Chromepet, Tambaram` *(optional)* |
| Maximum distance (km) from your area? | `5` |
| Bedrooms? | `1bhk` *(or `2bhk` / `3bhk` / `1rk`)* |
| How many people will live there? | `2` |
| Furnishing? | `any` *(or `furnished` / `semi-furnished` / `unfurnished`)* |
| Minimum monthly rent (₹)? | `5000` |
| Maximum monthly rent (₹)? | `15000` |
| Check every how many hours? | `1` |
| Telegram bot token + chat ID | *(paste what you got in step 2)* |

The wizard then:
- Geocodes your area name (no API key needed)
- Writes your settings to `config.py` and `.env`
- Sets the GitHub Actions secrets (via `gh` CLI if you have it)
- Updates the cron schedule to your chosen interval
- Commits + pushes — GitHub starts running it immediately
- Sends a "✅ Rental monitor configured" test message to your Telegram

**That's it.** You can close your laptop. GitHub runs the scan on schedule forever.

## Changing your settings later

Run the wizard again:

```bash
uv run python configure.py
```

Every prompt shows your current value in `[brackets]`. Press Enter to keep, type something new to change.

- **Moved cities?** Type the new city + new neighbourhood. It re-geocodes and re-runs from there.
- **Need a bigger budget?** Update min/max rent.
- **Want 2BHK instead?** Change the bedroom answer.
- **Too many alerts?** Increase the cycle hours.

## The daily digest

At 09:00 IST every day:

```
📋 Daily rental digest

Top 5 by fit score (last 24h):
• ₹10,000 — Adambakkam, Chennai · seen on 2
   [99acres] score 87 · <link>
...

Source health (24h):
✅ sulekha
✅ 99acres
⚠️ olx
❌ magicbricks
```

If a source has been silent for 3+ hours, the digest warns you — usually means the site started blocking us.

---

## For developers

### Run locally

```bash
uv run python run_once.py          # one scan cycle
uv run python monitor.py           # long-running loop
uv run python run_once.py --digest # send digest now
```

### Tests

```bash
uv run pytest -q
```

All adapter tests use checked-in HTML fixtures — no live network calls in CI.

### Manual config (skip the wizard)

- `config.py` — areas, budget, radius, bedrooms, etc.
- `.env` — Telegram secrets, location coordinates
- `.github/workflows/monitor.yml` — cron schedule

The wizard just writes these files for you.

### CI workflows

- `monitor.yml` — hourly cycle (wizard patches the interval)
- `digest.yml` — daily digest at 09:00 IST

Both restore `data/rental_monitor.db` from the `state` branch before running and write back on completion. **Don't push to the `state` branch by hand** — the workflows manage it.

### Cutover from v1

If you ran v1 before, seed the v2 dedup table so previously-seen listings don't re-alert:

```bash
uv run python scripts/seed_v2_seen.py legacy.db data/rental_monitor.db
```

### Project layout

```
rental-monitor/
├── configure.py            # the setup wizard
├── run_once.py             # one cycle (hourly cron + digest)
├── monitor.py              # long-running loop
├── config.py               # user settings (wizard writes this)
├── src/
│   ├── core/               # AsyncHttp, TokenBucket, Breaker, engine
│   ├── sources/            # SourceAdapter ABC + per-portal adapters + registry
│   ├── pipeline/           # filter, dedup, rank, enrich, prune, digest
│   ├── notifier/           # Telegram sender, alert_v2, digest
│   ├── state/              # aiosqlite connect + migrations
│   └── models.py           # pydantic Listing + RunStats
├── scripts/                # refresh_fixtures.py, seed_v2_seen.py
├── tests/                  # adapter + pipeline + unit tests + HTML fixtures
└── legacy/                 # v1 modules, kept until they're confirmed unneeded
```

### Working sources

Sulekha · SquareYards · 99acres · MagicBricks · OLX · DuckDuckGo

### Deferred sources

CommonFloor, NoBroker, Housing.com — these need browser DevTools recon to discover current API endpoints (their public search URLs return empty results or require session-issued IDs we can't guess). PR welcome if you capture the network calls.

### Getting API keys (free, no credit card)

| Service          | Link                       | Use                |
|------------------|----------------------------|--------------------|
| Telegram Bot     | @BotFather, /newbot        | Notifications      |
| Ola Maps         | maps.olacabs.com           | (Future) commute   |
| OpenRouteService | openrouteservice.org       | (Future) walking   |

`OLA_MAPS_API_KEY` and `ORS_API_KEY` are no-ops in v2.0.0 (heuristic commute is used). Env vars stay plumbed for the v2.1 commute integration.
