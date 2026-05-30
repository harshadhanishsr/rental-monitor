# Rental Monitor v2 — Design Spec

**Date:** 2026-05-29
**Status:** Approved (user) — pending spec-document-reviewer pass
**Scope:** Full coordinated rewrite (modern async stack, new scrapers, cross-source dedup, persistent state, observability)
**Hosting:** GitHub Actions hourly cron (unchanged)
**Budget:** $0 by default; optional `LLM_API_KEY` / `PROXY_URL` for graceful power-ups

---

## 1. Goals & non-goals

### Goals
- **Speed:** one cycle finishes in < 90 s wall clock (currently several minutes sequential).
- **Coverage:** restore the five currently-blocked sources (NoBroker, MagicBricks, Housing, OLX, plus DDG) using legitimate techniques (mobile/site JSON endpoints, sitemaps, `__NEXT_DATA__`, JSON-LD).
- **Signal quality:** one alert per physical unit even when the same flat appears on 3 sites. Fit-ranked.
- **Reliability:** durable state that survives GHA cache eviction; per-source circuit breakers; silent-source detection.
- **Politeness:** conservative rate limits, `robots.txt` awareness, retries with jitter, no aggressive evasion.

### Non-goals
- Web UI / dashboard (separate later project).
- Always-on hosting (stays on GH Actions cron).
- Paid services as a hard dependency (everything must work at $0).
- Adding sources outside the current portal set (no Facebook Marketplace, no PG-specific sites in v2).

### Success criteria
- Cycle wall-clock p50 ≤ 60 s, p95 ≤ 90 s on GH Actions `ubuntu-latest`.
- ≥ 8 of 9 retained sources return non-zero results in steady state.
- Cross-source dedup rate ≥ 30 % (i.e. ≥ 30 % of raw listings collapse into existing fingerprints).
- Zero duplicate alerts after GHA cache eviction (state-branch persistence).
- 80 % line coverage on `src/core/` and `src/pipeline/`.

---

## 2. Architecture

### Runtime shape

One run = one async event loop in a single GH Actions job, ≤ 2 min wall clock.

```
restore state branch ── load SQLite ──┐
                                       ├── async TaskGroup:
                                       │     scrape_sulekha   ─┐
                                       │     scrape_nobroker  ─┤
                                       │     scrape_99acres   ─┼── stream Listings into
                                       │     scrape_housing   ─┤    asyncio.Queue
                                       │     scrape_magic     ─┤
                                       │     scrape_squareyards┤
                                       │     scrape_commonfloor┤
                                       │     scrape_olx       ─┤
                                       │     scrape_ddg       ─┘
                                       │
                          dedup+rank ──┤  (consumer: fingerprint → fit score → gate)
                                       │
                          enrich  ──── │  (Ola Maps commute, only for unseen winners)
                                       │
                          alert   ──── │  (Telegram, parallel sends)
                                       │
                          persist ──── │  (mark_seen, write run-stats row)
                                       │
                       commit state ───┘  (force-push DB to state branch)
```

### Repo layout

```
rental-monitor/
├── monitor.py              # local daemon (loop wrapper around run_cycle)
├── run_once.py             # GH Actions entry (single cycle)
├── config.py               # unchanged user-facing config
├── pyproject.toml          # new — replaces requirements.txt, uv-managed
├── src/
│   ├── core/
│   │   ├── engine.py       # run_cycle orchestrator (the diagram above)
│   │   ├── http.py         # shared async client, impersonation, retries
│   │   ├── ratelimit.py    # per-host token bucket
│   │   └── circuit.py      # per-source open/half-open/closed breaker
│   ├── sources/            # adapters — one file per portal
│   │   ├── base.py         # SourceAdapter ABC
│   │   ├── sulekha.py
│   │   ├── nobroker.py
│   │   ├── ninetynine_acres.py
│   │   ├── magicbricks.py
│   │   ├── housing.py
│   │   ├── olx.py
│   │   ├── squareyards.py
│   │   ├── commonfloor.py
│   │   └── duckduckgo.py
│   ├── pipeline/
│   │   ├── dedup.py        # cross-source fingerprint
│   │   ├── rank.py         # fit score (+ optional LLM)
│   │   └── enrich.py       # travel time, geocode fallback
│   ├── state/
│   │   ├── db.py           # SQLite schema + migrations
│   │   ├── migrations/     # numbered .sql files
│   │   └── branch_sync.py  # restore/commit to `state` branch
│   ├── notifier/           # telegram_bot.py, tracker_bot.py (kept)
│   └── models.py           # Listing + RunStats (pydantic v2)
├── tests/
│   ├── fixtures/<source>/  # frozen HTML / JSON per source
│   ├── unit/
│   ├── adapter/
│   └── pipeline/
└── scripts/
    ├── refresh_fixtures.py # capture new snapshots when a site changes
    └── seed_v2_seen.py     # one-shot cutover helper
```

### Dependencies

| Dep | Why |
|---|---|
| `httpx[http2]` 0.27+ | Async HTTP, HTTP/2, connection pool |
| `curl_cffi` 0.7+ | Chrome TLS/JA3 impersonation |
| `playwright` 1.47+ async | Real-JS rendering for sites that need it |
| `selectolax` | Fast HTML parser (≈10× lxml) |
| `pydantic` v2 | Typed Listing/RunStats with JSON round-trip |
| `tenacity` | Retry/backoff with jitter |
| `aiosqlite` | Async SQLite |
| `uv` | Fast deps install in CI (≈5× pip) |

### Runtime guarantees

- Per-source failure never breaks the cycle (TaskGroup branches wrapped in try/except + circuit breaker).
- Cycle has a hard 90 s budget; outstanding sources cancelled cleanly.
- State always committed even on mid-cycle crash (`try/finally` in `run_once.py`).

---

## 3. Source adapter contract

```python
class SourceAdapter:
    name: ClassVar[str]                # "sulekha"
    rate: ClassVar[RateLimit]          # default 1 req/s, burst 3; overridable per source
    timeout_s: ClassVar[float] = 25.0
    needs_browser: ClassVar[bool] = False

    async def scrape(self, ctx: SourceCtx) -> AsyncIterator[Listing]: ...
```

`SourceCtx` carries:
- `http` — shared `httpx`/`curl_cffi` async session
- `browser` — lazily started Playwright context (only initialised if any adapter has `needs_browser=True`)
- `breaker` — circuit breaker for this source
- `logger` — pre-bound to `source` field
- `config` — user config module

The engine wraps each adapter call in:
- Circuit breaker — 3 consecutive failures → open until next cycle.
- Per-cycle deadline — default 30 s; engine cancels cleanly.
- Per-source token bucket — defaults to 1 req/s + burst 3.

### Per-source technique

| Source | Current | New technique |
|---|---|---|
| **Sulekha** | ✅ JSON-LD | Keep, async-ify |
| **99acres** | ✅ Playwright | Try `__NEXT_DATA__` first; fall back to Playwright |
| **NoBroker** | ❌ SPA | Public JSON endpoint (`/api/v1/property/filter/`) — same one the site's React frontend calls |
| **MagicBricks** | ❌ 403 | `curl_cffi` chrome110 impersonation + `__NEXT_DATA__` |
| **Housing.com** | ❌ 406 | Fix Accept header, parse `__NEXT_DATA__` |
| **OLX** | ❌ timeout | OLX's own `/api/relevance/v4/search` REST endpoint |
| **SquareYards** | ✅ JSON-LD | Keep, async-ify |
| **CommonFloor** | ✅ stateFromServer JSON | Keep, async-ify |
| **DuckDuckGo** | ✅ meta-search | Keep as discovery layer |
| **Quikr** | ❌ 404 | **Drop** — Quikr Homes shut down rentals in 2023 |

### Politeness defaults (in base adapter)

- Rate limit: 1 req/s + burst 3 per host (overridable).
- `If-Modified-Since` / `ETag` honored on repeat URL fetches.
- Tenacity backoff with jitter on 429/503; circuit opens after 3 in a row.
- Realistic UA, locale (`en-IN`), timezone (`Asia/Kolkata`).
- `robots.txt` checked once per cycle per host; non-compliant fetches logged as warnings (informational only — these pages are publicly served to user browsers).

### Discovery strategy

Two-phase only where useful:
1. **Discover** — `sitemap.xml` mining for sources that publish it (Housing, MagicBricks).
2. **Fetch + parse** — per URL via the technique above.

For sources whose search page returns full data (Sulekha JSON-LD, OLX API, NoBroker API), discovery is skipped — stream directly.

---

## 4. Dedup + ranking pipeline

### Cross-source fingerprint

```
fp = sha1(
    geohash7(lat, lng)         # ~150 m grid
    + "_" + price_bucket       # ₹500 rounding
    + "_" + bedrooms
    + "_" + furnishing_canon   # furnished | semi | unfurnished | unknown
)
```

Missing `lat/lng` fallback: `normalize_address(address)` (strip building numbers, lowercase, drop punctuation, collapse whitespace) in place of geohash. Price + bedrooms gate keeps false-merge rate low.

### Merge rule when two listings share a fingerprint

- Keep the one with `lat/lng` if only one has it.
- Keep richer `furnishing`, `rating`, longer `address`.
- Source preference: `nobroker > sulekha > 99acres > housing > magicbricks > squareyards > commonfloor > olx > duckduckgo` (NoBroker = direct landlord = highest signal).
- Track all source URLs in `Listing.also_seen_on: list[str]` → Telegram alert footer shows "Also on: Sulekha, 99acres".

### Fit score (deterministic, 0–100)

| Weight | Component | Formula |
|---|---|---|
| 40 | Commute | `40 * max(0, 1 - travel_min/60)` |
| 25 | Price | `25 * (MAX_RENT - price) / (MAX_RENT - MIN_RENT)` |
| 15 | Priority locality | 15 if in `PRIORITY_LOCALITIES` else 0 |
| 10 | Freshness | 10 on the cycle the fingerprint is `first_seen`, linear decay to 0 over 7 days from `first_seen` |
| 10 | Cross-source confirm | 5 per extra source, capped at 10 |

Used to **sort** alerts and gate the daily digest. Never filters — every match still gets one alert.

### Optional LLM layer (opt-in via `LLM_API_KEY`)

Three batched calls per cycle (≈ $0.001/cycle with Haiku):

1. **Address canonicalization** — one batch for listings missing `lat/lng`; returns `{locality, sublocality, landmark}`.
2. **Spam/fake detection** — flags suspiciously low price + vague address.
3. **Personalised re-rank** — uses last 30 d of `⭐ / 👎` tracker decisions to bump `fit_score` ± 10.

Code path identical with/without key (`if api_key: ...` wrapper).

### Pipeline ordering

```
raw → property_filter → distance_filter → dedup → enrich(commute) → rank → seen_filter → alert
```

- `dedup` before `enrich` → ~50 % reduction in Ola Maps calls.
- `seen_filter` last → fingerprint state still updated for confirmation-count purposes even on no-realert.

---

## 5. State management

### The `state` branch pattern

Dedicated `state` branch in the same repo, holding **only** `data/rental_monitor.db`. Single commit, force-pushed every run — branch never grows in history.

**Per-cycle flow:**
```
job start  ─► git fetch origin state ─► copy .db into workspace
              (if branch missing → init empty DB)
cycle runs ─► reads/writes data/rental_monitor.db
job end    ─► git checkout --orphan state-tmp
              git add data/rental_monitor.db
              git commit -m "state: <UTC ts> · N new · M total"
              git push --force origin state-tmp:state
```

**Why force-push is safe:** the branch is data, not code. Nobody branches from it. Commit message = audit log.

**Bootstrap:** on first run, `branch_sync.restore()` notices `state` doesn't exist → creates empty DB → first push creates the branch.

**Concurrency:** workflow `concurrency:` group `rental-monitor` with `cancel-in-progress: false` → no two cycles race on the branch.

### Schema

```sql
CREATE TABLE listings (
    fingerprint  TEXT PRIMARY KEY,
    first_seen   INTEGER NOT NULL,
    last_seen    INTEGER NOT NULL,
    sources      TEXT NOT NULL,    -- JSON list
    canonical    TEXT NOT NULL,    -- JSON of best merged Listing
    alerted_at   INTEGER,
    msg_id       INTEGER
);
CREATE INDEX idx_listings_last_seen ON listings(last_seen);

CREATE TABLE tracker (
    tracking_id  TEXT PRIMARY KEY,
    fingerprint  TEXT NOT NULL REFERENCES listings(fingerprint),
    status       TEXT NOT NULL,    -- new|shortlisted|contacted|passed
    updated_at   INTEGER NOT NULL
);

CREATE TABLE runs (
    run_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at    INTEGER NOT NULL,
    duration_ms   INTEGER NOT NULL,
    raw_count     INTEGER NOT NULL,
    after_filter  INTEGER NOT NULL,
    after_dedup   INTEGER NOT NULL,
    alerted       INTEGER NOT NULL,
    per_source    TEXT NOT NULL,    -- JSON {sulekha:{scraped,kept,errored,ms}, ...}
    breaker_open  TEXT NOT NULL     -- JSON list of sources skipped
);

CREATE TABLE travel_cache (
    cache_key   TEXT PRIMARY KEY,   -- "lat1,lng1_lat2,lng2_mode"
    minutes     REAL NOT NULL,
    source      TEXT NOT NULL,      -- ola | ors | heuristic
    cached_at   INTEGER NOT NULL
);

CREATE TABLE pending_alerts (
    pending_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint   TEXT NOT NULL REFERENCES listings(fingerprint),
    queued_at     INTEGER NOT NULL,
    retry_count   INTEGER NOT NULL DEFAULT 0,
    last_error    TEXT
);
CREATE INDEX idx_pending_queued ON pending_alerts(queued_at);

CREATE TABLE schema_version (version INTEGER PRIMARY KEY);
```

Pending-alert retries are processed at the **start** of each cycle before scraping, with a max of 48 retries before the row is dropped (mirrors current `delete_stale_pending` behaviour).

Migrations: numbered `src/state/migrations/00N_*.sql`, applied in order, tracked in `schema_version`. No alembic — plain SQL.

### Prune policy (end of every cycle)

- `listings`: drop where `last_seen < now − 60 d AND alerted_at IS NULL`.
- `listings`: drop where `last_seen < now − 180 d` (even if alerted).
- `runs`: keep last 100 rows.
- `travel_cache`: drop rows older than 30 d.
- `VACUUM` if blob > 5 MB.

Steady-state DB size: **~1–3 MB**.

### Disaster recovery

- DB lives in repo branch → cloning gives full state.
- Worst case (corruption): delete `state` branch → next run bootstraps empty → ≤ 1 cycle of duplicate alerts → steady state resumes.
- Optional manual backup: `git push backup state:state-$(date +%F)` for timestamped snapshots.

---

## 6. Error handling & observability

### Per-layer failure model

| Layer | Failure type | Behaviour |
|---|---|---|
| HTTP request | timeout / 5xx / 429 | Tenacity retry: 3 attempts, exp backoff (1 s / 2 s / 4 s) + jitter |
| Parser | JSON-LD missing, regex no-match | Log WARN with first 200 chars of HTML, return empty — never raise |
| Source adapter | exception | Circuit breaker increments; 3 in a row → open for the rest of this cycle and the next |
| Cycle orchestrator | one source's TaskGroup branch crashes | Each branch wrapped in try/except to isolate (TaskGroup would otherwise cancel siblings) |
| Cycle | 90 s budget exceeded | Remaining tasks cancelled; partial results still alert |
| State write | git push fails | Retry once with `git pull --rebase` then push; on second fail → save DB to GH Actions artifact as fallback |
| Telegram send | HTTP fail | Retry 3×; if still failing → row added to `pending_alerts` table (see schema addendum below) |

### Observability surfaces

- **Per-cycle log** to `data/monitor.log` + GH Actions job log: structured JSON, one line per source: `{source, scraped, kept, errored, duration_ms, breaker_state}`.
- **`runs` table** — queryable history.
- **Daily Telegram digest** at 09:00 IST — separate GH Actions workflow invoking `run_once.py --digest`: posts top 5 listings of last 24 h by fit score + per-source health (✅/⚠️/❌). No scrape, read-only over the `runs` and `listings` tables.
- **Silent-source detector**: if a source returns 0 listings for 3 consecutive cycles, the daily digest flags it.

---

## 7. Testing strategy

TDD-style. Each adapter ships with its own frozen-HTML fixture so tests never depend on live sites.

| Level | Coverage | Tool |
|---|---|---|
| Unit | `dedup.fingerprint`, `rank.score`, `Listing` validators, address normalizer | pytest |
| Adapter | each source's `scrape()` against captured fixture in `tests/fixtures/<source>/` | pytest + `respx` (httpx mock) |
| Pipeline | full `engine.run_cycle` against in-memory SQLite + mocked sources | pytest-asyncio |
| Smoke (CI optional) | live fetch of 1 URL per source, assert ≥ 1 listing parsed | nightly job, non-blocking |

- Fixture refresh: `scripts/refresh_fixtures.py <source>` re-downloads + re-saves snapshots.
- Coverage target: 80 % line on `src/pipeline/` and `src/core/`; adapters at "happy path + 1 malformed input" minimum.
- No flaky tests: no test may hit a live host in default `pytest`. Live smoke = opt-in `pytest -m smoke`.

---

## 8. Migration plan

Feature branch `upgrade/v2`. Six checkpoints, each independently mergeable.

1. **Scaffold + state branch.** Empty `src/core`, `src/state`, `state` branch bootstrap. Old `monitor.py` still runs. Confirm `state` branch round-trip works in CI.
2. **Models + pipeline (no scrapers yet).** `Listing` pydantic, dedup, rank, `runs` table. Unit-tested. Old scrapers feed new pipeline via thin adapter shim.
3. **Migrate working scrapers.** Sulekha, SquareYards, CommonFloor, 99acres, DuckDuckGo → new adapter contract. Each migration = one PR with fixture + tests.
4. **Resurrect blocked scrapers.** NoBroker API, MagicBricks, Housing, OLX. Each in its own PR, validated against captured fixtures.
5. **Switch entry points.** `run_once.py` and `monitor.py` import from `src.core.engine`. Old code paths kept under `legacy/` for one week.
6. **Cleanup.** Delete `legacy/`, drop Quikr, update README, tag `v2.0.0`.

**During cutover (steps 2–5):** the existing `src/scheduler.py` (current orchestrator, invoked by today's `monitor.py` and `run_once.py`) and the new `src/core/engine.py` both write to the same DB but use **separate seen-key namespaces** (`solo` vs `v2`). One-shot `scripts/seed_v2_seen.py` copies old `seen` rows into the new fingerprint format before step 5 to avoid a re-alert burst.

**Rollback:** any step is one-PR-revert safe. State branch unaffected because old/new use separate namespaces in the same DB.

---

## 9. Open questions deferred to plan

- Exact NoBroker API URL/params shape (needs network-tab capture during plan phase).
- Whether `playwright-stealth` 1.x is compatible with playwright 1.47+ — if not, evaluate `rebrowser-playwright` or hand-roll fingerprint patches.
- Telegram tracker bot polling vs webhook — webhook requires public URL, polling is fine for GH-Actions-driven model but adds latency on button presses. Probably keep polling.

---

## 10. Out of scope (explicit YAGNI)

- Web dashboard.
- Multi-user / SaaS form factor.
- Real-time push (websocket / SSE) — hourly cron is enough for rental market velocity.
- Mobile app.
- New cities other than the user's current configuration (Chennai — but the design stays city-agnostic via `config.py`).
- Auto-scheduling viewings, contact form automation, landlord messaging.
