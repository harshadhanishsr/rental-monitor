# Rental Monitor v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite rental-monitor as an async, dedup-first, durable-state scraper that runs in ≤ 90 s per cycle on GitHub Actions and restores the five currently-blocked sources.

**Architecture:** Single async event loop per cycle. Each source is an isolated `SourceAdapter`. Listings stream through dedup → enrich → rank → seen-filter → alert. State lives in a force-pushed `state` branch as `data/rental_monitor.db`. See `docs/superpowers/specs/2026-05-29-rental-monitor-upgrade-design.md` for the full design.

**Tech Stack:** Python 3.12, `httpx[http2]`, `curl_cffi`, `playwright` (async), `selectolax`, `pydantic` v2, `tenacity`, `aiosqlite`, `uv`, pytest + pytest-asyncio + respx.

---

## File structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | Replace `requirements.txt`; uv-managed lockfile |
| `src/models.py` | `Listing`, `RunStats` pydantic v2 models |
| `src/core/http.py` | Shared async httpx + curl_cffi clients, retry policy |
| `src/core/ratelimit.py` | Per-host token bucket |
| `src/core/circuit.py` | Per-source circuit breaker |
| `src/core/engine.py` | `run_cycle()` orchestrator + `--digest` mode |
| `src/sources/base.py` | `SourceAdapter` ABC + `SourceCtx` |
| `src/sources/<name>.py` | One file per portal |
| `src/pipeline/dedup.py` | `fingerprint()`, `merge()` |
| `src/pipeline/rank.py` | Deterministic fit-score + optional LLM hook |
| `src/pipeline/enrich.py` | Travel time wrapper (uses existing `src/travel_time.py`) |
| `src/state/db.py` | `aiosqlite` connection, migrations |
| `src/state/migrations/001_init.sql` | Initial schema (Section 5 of spec) |
| `src/state/branch_sync.py` | Restore/commit `state` branch |
| `.github/workflows/monitor.yml` | Updated for uv + state branch |
| `.github/workflows/digest.yml` | New daily digest workflow |
| `scripts/refresh_fixtures.py` | Capture HTML/JSON snapshots per source |
| `scripts/seed_v2_seen.py` | One-shot legacy → v2 namespace migration |
| `tests/fixtures/<source>/*.{html,json}` | Frozen response snapshots |

**Legacy code (kept until Phase 5, deleted in Phase 6):** `src/scheduler.py`, `src/scrapers/*.py`, `src/db.py`.

---

# Phase 1 — Scaffold + state branch

**Outcome:** Empty new tree compiles, `state` branch round-trips via CI, old monitor still runs unchanged.

## Task 1.1: Create branch and switch to uv

**Files:**
- Create: `pyproject.toml`
- Delete: `requirements.txt` (after lockfile generated)

- [ ] **Step 1: Create feature branch**

```bash
cd C:\Users\harsh\projects\rental-monitor
git checkout -b upgrade/v2
```

- [ ] **Step 2: Write pyproject.toml**

```toml
[project]
name = "rental-monitor"
version = "2.0.0-dev"
requires-python = ">=3.12"
dependencies = [
    "httpx[http2]>=0.27",
    "curl-cffi>=0.7",
    "playwright>=1.47",
    "selectolax>=0.3.21",
    "pydantic>=2.7",
    "tenacity>=8.3",
    "aiosqlite>=0.20",
    "python-dotenv>=1.0",
    "geopy>=2.4",
    "haversine>=2.8",
    "requests>=2.32",
    "twilio>=9.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.1",
    "pytest-asyncio>=0.23",
    "pytest-mock>=3.14",
    "respx>=0.21",
    "coverage>=7.5",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = ["smoke: live-fetch integration tests (opt-in)"]
testpaths = ["tests"]
```

- [ ] **Step 3: Install with uv and verify**

```bash
uv sync --all-extras
uv run python -c "import httpx, curl_cffi, pydantic, aiosqlite; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git rm requirements.txt
git commit -m "build: switch to pyproject.toml + uv (v2 scaffold)"
```

## Task 1.2: Branch sync module

**Files:**
- Create: `src/state/__init__.py`
- Create: `src/state/branch_sync.py`
- Create: `tests/unit/test_branch_sync.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_branch_sync.py
from pathlib import Path
from src.state.branch_sync import build_orphan_commit_args

def test_orphan_commit_args_includes_db_path():
    args = build_orphan_commit_args(db_path=Path("data/rental_monitor.db"),
                                    message="state: test")
    assert "--orphan" in args["checkout"]
    assert "state-tmp" in args["checkout"]
    assert "data/rental_monitor.db" in args["add"]
    assert args["commit_msg"] == "state: test"
    assert args["push_refspec"] == "state-tmp:state"
```

- [ ] **Step 2: Run test, confirm failure**

```bash
uv run pytest tests/unit/test_branch_sync.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.state.branch_sync'`

- [ ] **Step 3: Implement**

```python
# src/state/branch_sync.py
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)
BRANCH = "state"
WORK_BRANCH = "state-tmp"


def build_orphan_commit_args(db_path: Path, message: str) -> dict:
    return {
        "checkout": ["git", "checkout", "--orphan", WORK_BRANCH],
        "add":     ["git", "add", "-f", str(db_path)],
        "commit_msg": message,
        "push_refspec": f"{WORK_BRANCH}:{BRANCH}",
    }


def _run(cmd: list[str], check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    logger.debug("git: %s", " ".join(cmd))
    return subprocess.run(cmd, check=check,
                          capture_output=capture, text=True)


def restore(db_path: Path) -> bool:
    """Fetch state branch and check out the DB file. Returns True if restored."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    r = _run(["git", "fetch", "origin", BRANCH], check=False, capture=True)
    if r.returncode != 0:
        logger.info("state branch not found — bootstrapping empty DB")
        return False
    _run(["git", "checkout", f"origin/{BRANCH}", "--", str(db_path)])
    logger.info("state branch restored: %s", db_path)
    return True


def commit_and_push(db_path: Path, message: str,
                    artifact_dir: Path | None = None) -> None:
    """Force-push DB as single-commit orphan branch.

    On push failure: retry once with `git pull --rebase`; on second fail,
    copy DB to `artifact_dir` (caller uploads it via actions/upload-artifact).
    """
    args = build_orphan_commit_args(db_path, message)
    _run(args["checkout"])
    _run(args["add"])
    _run(["git", "commit", "-m", args["commit_msg"]])
    push = _run(["git", "push", "--force", "origin", args["push_refspec"]],
                check=False, capture=True)
    if push.returncode != 0:
        logger.warning("push failed (%s), retrying after pull --rebase",
                       push.stderr.strip())
        _run(["git", "pull", "--rebase", "origin", BRANCH], check=False)
        push2 = _run(["git", "push", "--force", "origin", args["push_refspec"]],
                     check=False, capture=True)
        if push2.returncode != 0:
            if artifact_dir is not None:
                artifact_dir.mkdir(parents=True, exist_ok=True)
                import shutil
                shutil.copy2(db_path, artifact_dir / db_path.name)
                logger.error("push failed twice — DB saved to %s", artifact_dir)
            raise RuntimeError(f"state push failed: {push2.stderr.strip()}")
    _run(["git", "checkout", "-"])
```

- [ ] **Step 4: Run test**

```bash
uv run pytest tests/unit/test_branch_sync.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/state/__init__.py src/state/branch_sync.py tests/unit/__init__.py tests/unit/test_branch_sync.py
git commit -m "feat(state): add state-branch sync module"
```

## Task 1.3: GH Actions workflow with state branch

**Files:**
- Modify: `.github/workflows/monitor.yml`

- [ ] **Step 1: Replace workflow**

```yaml
name: Rental Monitor
on:
  schedule:
    - cron: '0 * * * *'
  workflow_dispatch:

concurrency:
  group: rental-monitor
  cancel-in-progress: false

jobs:
  scan:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: astral-sh/setup-uv@v3
      - run: uv sync
      - run: uv run playwright install --with-deps chromium
      - name: Restore state branch
        run: |
          git config user.name  "rental-monitor-bot"
          git config user.email "bot@users.noreply.github.com"
          uv run python -c "from pathlib import Path; from src.state.branch_sync import restore; restore(Path('data/rental_monitor.db'))"
      - name: Run cycle
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID:   ${{ secrets.TELEGRAM_CHAT_ID }}
          OLA_MAPS_API_KEY:   ${{ secrets.OLA_MAPS_API_KEY }}
          ORS_API_KEY:        ${{ secrets.ORS_API_KEY }}
          OFFICE_LAT:         ${{ secrets.OFFICE_LAT }}
          OFFICE_LNG:         ${{ secrets.OFFICE_LNG }}
          LLM_API_KEY:        ${{ secrets.LLM_API_KEY }}
          PROXY_URL:          ${{ secrets.PROXY_URL }}
          DB_PATH:            data/rental_monitor.db
        run: uv run python run_once.py
      - name: Persist state
        if: always()
        run: |
          uv run python -c "import datetime; from pathlib import Path; from src.state.branch_sync import commit_and_push; commit_and_push(Path('data/rental_monitor.db'), f'state: {datetime.datetime.utcnow().isoformat()}Z')"
```

- [ ] **Step 2: Verify YAML parses**

```bash
uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/monitor.yml'))"
```

Expected: no exception.

- [ ] **Step 3: Commit and push for live CI test**

```bash
git add .github/workflows/monitor.yml
git commit -m "ci: wire state-branch sync into workflow"
git push -u origin upgrade/v2
```

Then on GitHub Actions, click **Run workflow** on `upgrade/v2`. Expect: green run, `state` branch appears in repo with one commit holding the DB.

- [ ] **Step 4: Verify**

```bash
git fetch origin state
git log --oneline origin/state -n 1
```

Expected: one commit titled `state: <iso ts>Z`.

---

# Phase 2 — Models, core engine, pipeline (no new scrapers yet)

**Outcome:** New pipeline runs end-to-end fed by *old* scrapers via a shim. Tests pass. Old `run_once.py` still works in parallel.

## Task 2.1: Listing model (pydantic v2)

**Files:**
- Create: `tests/unit/test_models.py`
- Replace: `src/models.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_models.py
from src.models import Listing

def test_listing_round_trip():
    src = {"id": "sulekha_1", "source": "sulekha", "title": "1BHK Pallavaram",
           "address": "Pallavaram, Chennai", "price": 12000,
           "url": "https://x", "lat": 13.0, "lng": 80.1}
    l = Listing.model_validate(src)
    assert l.also_seen_on == []
    assert Listing.model_validate_json(l.model_dump_json()) == l

def test_listing_rejects_negative_price():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Listing(id="x", source="y", title="t", address="a",
                price=-1, url="https://x")
```

- [ ] **Step 2: Run, confirm failure**

```bash
uv run pytest tests/unit/test_models.py -v
```

Expected: ImportError or AttributeError.

- [ ] **Step 3: Implement**

```python
# src/models.py
from __future__ import annotations
from pydantic import BaseModel, Field, PositiveInt, HttpUrl, ConfigDict

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
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/test_models.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/models.py tests/unit/test_models.py
git commit -m "feat(models): pydantic v2 Listing + RunStats"
```

## Task 2.2: Dedup fingerprint

**Files:**
- Create: `src/pipeline/__init__.py`, `src/pipeline/dedup.py`
- Create: `tests/unit/test_dedup.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_dedup.py
from src.models import Listing
from src.pipeline.dedup import fingerprint, merge

A = Listing(id="sulekha_1", source="sulekha", title="1BHK Pallavaram",
            address="123 Foo St, Pallavaram, Chennai", price=11800,
            url="https://s/1", lat=12.974, lng=80.143, furnishing="semi-furnished")
B = Listing(id="99acres_2", source="99acres", title="1 BHK Pallavaram",
            address="Foo St, Pallavaram", price=12200,
            url="https://9/2", lat=12.974, lng=80.143, furnishing="semi-furnished")

def test_same_unit_same_fingerprint():
    assert fingerprint(A) == fingerprint(B)

def test_merge_prefers_nobroker_url_order():
    nb = A.model_copy(update={"source": "nobroker", "id": "nb_3"})
    merged = merge([A, nb])
    assert merged.source == "nobroker"
    assert set(merged.also_seen_on) >= {"https://s/1"}

def test_no_latlng_falls_back_to_address():
    a = A.model_copy(update={"lat": None, "lng": None})
    b = B.model_copy(update={"lat": None, "lng": None,
                             "address": "123 Foo Street Pallavaram Chennai"})
    assert fingerprint(a) == fingerprint(b)
```

- [ ] **Step 2: Run, confirm failure**

```bash
uv run pytest tests/unit/test_dedup.py -v
```

- [ ] **Step 3: Implement**

```python
# src/pipeline/dedup.py
from __future__ import annotations
import hashlib
import re
from src.models import Listing

SOURCE_RANK = {
    "nobroker": 0, "sulekha": 1, "99acres": 2, "housing": 3,
    "magicbricks": 4, "squareyards": 5, "commonfloor": 6,
    "olx": 7, "duckduckgo": 8,
}

_GEOHASH_B32 = "0123456789bcdefghjkmnpqrstuvwxyz"


def geohash(lat: float, lng: float, precision: int = 7) -> str:
    lat_lo, lat_hi = -90.0, 90.0
    lng_lo, lng_hi = -180.0, 180.0
    bits, hash_chars, ch_bits, even = [], [], 0, True
    while len(hash_chars) < precision:
        if even:
            mid = (lng_lo + lng_hi) / 2
            bit = 1 if lng > mid else 0
            (lng_lo, lng_hi) = (mid, lng_hi) if bit else (lng_lo, mid)
        else:
            mid = (lat_lo + lat_hi) / 2
            bit = 1 if lat > mid else 0
            (lat_lo, lat_hi) = (mid, lat_hi) if bit else (lat_lo, mid)
        bits.append(bit)
        ch_bits += 1
        even = not even
        if ch_bits == 5:
            idx = bits[-5] * 16 + bits[-4] * 8 + bits[-3] * 4 + bits[-2] * 2 + bits[-1]
            hash_chars.append(_GEOHASH_B32[idx])
            ch_bits = 0
    return "".join(hash_chars)


def _norm_addr(addr: str) -> str:
    s = addr.lower()
    s = re.sub(r"\d+[a-z]?[/-]?\d*", " ", s)  # strip building numbers
    s = re.sub(r"[^a-z\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _bedrooms(title: str) -> int:
    m = re.search(r"(\d)\s*(bhk|rk)", title.lower())
    return int(m.group(1)) if m else 1


def _furn_canon(f: str) -> str:
    f = (f or "unknown").lower()
    if "unfurn" in f: return "unfurnished"
    if "semi" in f:   return "semi"
    if "furn" in f:   return "furnished"
    return "unknown"


def fingerprint(l: Listing) -> str:
    if l.lat is not None and l.lng is not None:
        loc = geohash(l.lat, l.lng, 7)
    else:
        loc = _norm_addr(l.address)
    price_bucket = round(l.price / 500) * 500
    key = f"{loc}_{price_bucket}_{_bedrooms(l.title)}_{_furn_canon(l.furnishing)}"
    return hashlib.sha1(key.encode()).hexdigest()


def merge(listings: list[Listing]) -> Listing:
    best = sorted(listings, key=lambda x: SOURCE_RANK.get(x.source, 99))[0]
    others = [l for l in listings if l.url != best.url]
    return best.model_copy(update={
        "also_seen_on": sorted({l.url for l in others}),
        "lat": best.lat or next((l.lat for l in listings if l.lat), None),
        "lng": best.lng or next((l.lng for l in listings if l.lng), None),
        "rating": max((l.rating for l in listings if l.rating is not None), default=None),
        "fingerprint": fingerprint(best),
    })
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/test_dedup.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/__init__.py src/pipeline/dedup.py tests/unit/test_dedup.py
git commit -m "feat(pipeline): cross-source fingerprint + merge"
```

## Task 2.3: Fit-score ranking

**Files:**
- Create: `src/pipeline/rank.py`
- Create: `tests/unit/test_rank.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_rank.py
import time
from src.models import Listing
from src.pipeline.rank import fit_score

L = Listing(id="x", source="sulekha", title="1BHK",
            address="Pallikaranai, Chennai", price=10000, url="https://x",
            lat=12.97, lng=80.20)

def test_score_in_range():
    score = fit_score(L, travel_min=25, first_seen_ts=int(time.time()),
                      now_ts=int(time.time()), confirm_count=1,
                      priority=True, max_rent=15000, min_rent=3000)
    assert 0 <= score <= 100

def test_priority_locality_bumps_score():
    base = fit_score(L, travel_min=25, first_seen_ts=int(time.time()),
                     now_ts=int(time.time()), confirm_count=1, priority=False,
                     max_rent=15000, min_rent=3000)
    boost = fit_score(L, travel_min=25, first_seen_ts=int(time.time()),
                      now_ts=int(time.time()), confirm_count=1, priority=True,
                      max_rent=15000, min_rent=3000)
    assert boost - base == 15
```

- [ ] **Step 2: Run, confirm failure**

```bash
uv run pytest tests/unit/test_rank.py -v
```

- [ ] **Step 3: Implement**

```python
# src/pipeline/rank.py
from src.models import Listing

DAY = 86400


def fit_score(l: Listing, *, travel_min: float | None, first_seen_ts: int,
              now_ts: int, confirm_count: int, priority: bool,
              max_rent: int, min_rent: int) -> int:
    if travel_min is not None:
        commute = 40 * max(0.0, 1 - travel_min / 60)
    else:
        commute = 0.0
    price_span = max_rent - min_rent or 1
    price = 25 * max(0.0, (max_rent - l.price) / price_span)
    locality = 15 if priority else 0
    age_days = max(0, (now_ts - first_seen_ts) / DAY)
    freshness = 10 * max(0.0, 1 - age_days / 7)
    confirm = min(10, max(0, confirm_count - 1) * 5)
    return int(round(commute + price + locality + freshness + confirm))
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/test_rank.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/rank.py tests/unit/test_rank.py
git commit -m "feat(pipeline): deterministic fit score"
```

## Task 2.4: Initial DB schema + migrations

**Files:**
- Create: `src/state/migrations/001_init.sql`
- Create: `src/state/db.py`
- Create: `tests/unit/test_db.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_db.py
import pytest
from pathlib import Path
from src.state.db import connect, migrate

@pytest.mark.asyncio
async def test_migrate_creates_listings_table(tmp_path: Path):
    db = tmp_path / "t.db"
    async with connect(db) as conn:
        await migrate(conn)
        rows = await (await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
    names = {r[0] for r in rows}
    assert {"listings", "tracker", "runs", "travel_cache",
            "pending_alerts", "schema_version"} <= names
```

- [ ] **Step 2: Run, confirm failure**

```bash
uv run pytest tests/unit/test_db.py -v
```

- [ ] **Step 3: Write the SQL migration**

```sql
-- src/state/migrations/001_init.sql
CREATE TABLE listings (
    fingerprint  TEXT PRIMARY KEY,
    first_seen   INTEGER NOT NULL,
    last_seen    INTEGER NOT NULL,
    sources      TEXT NOT NULL,
    canonical    TEXT NOT NULL,
    alerted_at   INTEGER,
    msg_id       INTEGER
);
CREATE INDEX idx_listings_last_seen ON listings(last_seen);

CREATE TABLE tracker (
    tracking_id  TEXT PRIMARY KEY,
    fingerprint  TEXT NOT NULL REFERENCES listings(fingerprint),
    status       TEXT NOT NULL,
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
    per_source    TEXT NOT NULL,
    breaker_open  TEXT NOT NULL
);

CREATE TABLE travel_cache (
    cache_key   TEXT PRIMARY KEY,
    minutes     REAL NOT NULL,
    source      TEXT NOT NULL,
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
INSERT INTO schema_version (version) VALUES (1);
```

- [ ] **Step 4: Implement async DB module**

```python
# src/state/db.py
from __future__ import annotations
import aiosqlite
from contextlib import asynccontextmanager
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


@asynccontextmanager
async def connect(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(db_path)
    await conn.execute("PRAGMA foreign_keys = ON")
    await conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
    finally:
        await conn.commit()
        await conn.close()


async def _current_version(conn: aiosqlite.Connection) -> int:
    try:
        row = await (await conn.execute(
            "SELECT MAX(version) FROM schema_version")).fetchone()
        return row[0] or 0
    except aiosqlite.OperationalError:
        return 0


async def migrate(conn: aiosqlite.Connection) -> None:
    current = await _current_version(conn)
    for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = int(sql_file.stem.split("_")[0])
        if version <= current:
            continue
        await conn.executescript(sql_file.read_text())
        await conn.commit()
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/unit/test_db.py -v
```

Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add src/state/db.py src/state/migrations/001_init.sql tests/unit/test_db.py
git commit -m "feat(state): aiosqlite + schema migrations"
```

## Task 2.5: Rate limiter + circuit breaker

**Files:**
- Create: `src/core/__init__.py`, `src/core/ratelimit.py`, `src/core/circuit.py`
- Create: `tests/unit/test_ratelimit.py`, `tests/unit/test_circuit.py`

- [ ] **Step 1: Write failing tests for both**

```python
# tests/unit/test_ratelimit.py
import asyncio, time, pytest
from src.core.ratelimit import TokenBucket

@pytest.mark.asyncio
async def test_bucket_throttles():
    b = TokenBucket(rate=10, burst=2)  # 10/s
    start = time.monotonic()
    for _ in range(4):
        await b.acquire()
    # 2 free + 2 throttled at 10/s = ~0.2s
    assert time.monotonic() - start >= 0.15
```

```python
# tests/unit/test_circuit.py
import pytest
from src.core.circuit import Breaker, BreakerOpen

def test_opens_after_threshold():
    b = Breaker(threshold=3)
    for _ in range(3): b.record_failure()
    assert b.is_open

def test_success_resets():
    b = Breaker(threshold=3)
    b.record_failure()
    b.record_success()
    assert not b.is_open

def test_check_raises_when_open():
    b = Breaker(threshold=1)
    b.record_failure()
    with pytest.raises(BreakerOpen):
        b.check()
```

- [ ] **Step 2: Confirm failures**

```bash
uv run pytest tests/unit/test_ratelimit.py tests/unit/test_circuit.py -v
```

- [ ] **Step 3: Implement**

```python
# src/core/ratelimit.py
import asyncio, time

class TokenBucket:
    def __init__(self, rate: float, burst: int):
        self.rate, self.capacity = rate, burst
        self.tokens = float(burst)
        self.updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
            self.updated = now
            if self.tokens < 1:
                await asyncio.sleep((1 - self.tokens) / self.rate)
                self.tokens = 0
            else:
                self.tokens -= 1
```

```python
# src/core/circuit.py
class BreakerOpen(Exception): ...

class Breaker:
    def __init__(self, threshold: int = 3):
        self.threshold = threshold
        self.failures = 0

    @property
    def is_open(self) -> bool: return self.failures >= self.threshold

    def record_failure(self) -> None: self.failures += 1
    def record_success(self) -> None: self.failures = 0
    def check(self) -> None:
        if self.is_open: raise BreakerOpen()
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/ -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/core/__init__.py src/core/ratelimit.py src/core/circuit.py tests/unit/test_ratelimit.py tests/unit/test_circuit.py
git commit -m "feat(core): token-bucket rate limit + circuit breaker"
```

## Task 2.6: HTTP client wrapper

**Files:**
- Create: `src/core/http.py`
- Create: `tests/unit/test_http.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_http.py
import httpx, pytest, respx
from src.core.http import AsyncHttp

@pytest.mark.asyncio
async def test_retries_on_5xx(respx_mock):
    route = respx_mock.get("https://example.com/").mock(side_effect=[
        httpx.Response(503), httpx.Response(503), httpx.Response(200, text="ok")
    ])
    async with AsyncHttp(retries=3, backoff_base=0) as http:
        r = await http.get("https://example.com/")
    assert r.status_code == 200
    assert route.call_count == 3
```

- [ ] **Step 2: Confirm failure**

```bash
uv run pytest tests/unit/test_http.py -v
```

- [ ] **Step 3: Implement**

```python
# src/core/http.py
from __future__ import annotations
import httpx
from tenacity import (AsyncRetrying, retry_if_exception_type,
                      stop_after_attempt, wait_exponential_jitter)

_DEFAULT_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0.0.0 Safari/537.36"),
    "Accept-Language": "en-IN,en;q=0.9",
}


class _RetryStatus(Exception):
    def __init__(self, response: httpx.Response): self.response = response


class AsyncHttp:
    def __init__(self, *, retries: int = 3, backoff_base: float = 1.0,
                 timeout: float = 25.0, proxy: str | None = None):
        self._client = httpx.AsyncClient(
            http2=True, follow_redirects=True, timeout=timeout,
            headers=_DEFAULT_HEADERS, proxy=proxy,
        )
        self._retrying = AsyncRetrying(
            stop=stop_after_attempt(retries),
            wait=wait_exponential_jitter(initial=backoff_base, max=8),
            retry=retry_if_exception_type((httpx.TransportError, _RetryStatus)),
            reraise=True,
        )

    async def __aenter__(self): return self
    async def __aexit__(self, *exc): await self._client.aclose()

    async def get(self, url: str, **kw) -> httpx.Response:
        async for attempt in self._retrying:
            with attempt:
                r = await self._client.get(url, **kw)
                if r.status_code in (429, 502, 503, 504):
                    raise _RetryStatus(r)
                return r
        raise RuntimeError("unreachable")
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/unit/test_http.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/core/http.py tests/unit/test_http.py
git commit -m "feat(core): async http client with retry/backoff"
```

## Task 2.7: Source adapter ABC

**Files:**
- Create: `src/sources/__init__.py`, `src/sources/base.py`

- [ ] **Step 1: Write the ABC**

```python
# src/sources/base.py
from __future__ import annotations
import abc
from dataclasses import dataclass
from typing import AsyncIterator, ClassVar
from src.core.circuit import Breaker
from src.core.http import AsyncHttp
from src.core.ratelimit import TokenBucket
from src.models import Listing


@dataclass
class RateLimit:
    rate: float = 1.0     # req/s
    burst: int = 3


@dataclass
class SourceCtx:
    http: AsyncHttp
    bucket: TokenBucket
    breaker: Breaker
    logger: object
    config: object
    browser: object | None = None  # lazy Playwright


class SourceAdapter(abc.ABC):
    name: ClassVar[str] = "abstract"
    rate: ClassVar[RateLimit] = RateLimit()
    timeout_s: ClassVar[float] = 25.0
    needs_browser: ClassVar[bool] = False

    @abc.abstractmethod
    async def scrape(self, ctx: SourceCtx) -> AsyncIterator[Listing]: ...
```

- [ ] **Step 2: Verify import**

```bash
uv run python -c "from src.sources.base import SourceAdapter; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add src/sources/__init__.py src/sources/base.py
git commit -m "feat(sources): adapter ABC + SourceCtx"
```

## Task 2.8: Engine skeleton

**Files:**
- Create: `src/core/engine.py`
- Create: `tests/pipeline/test_engine.py`

- [ ] **Step 1: Write failing test**

```python
# tests/pipeline/test_engine.py
import pytest, time
from typing import AsyncIterator
from src.core.engine import run_cycle, EngineConfig
from src.models import Listing
from src.sources.base import SourceAdapter, SourceCtx, RateLimit


class FakeSource(SourceAdapter):
    name = "fake"
    rate = RateLimit(rate=100, burst=10)

    async def scrape(self, ctx: SourceCtx) -> AsyncIterator[Listing]:
        for i in range(3):
            yield Listing(id=f"f{i}", source="fake", title="1BHK",
                          address="Pallavaram, Chennai", price=10000 + i,
                          url=f"https://f/{i}", lat=12.97, lng=80.18)


@pytest.mark.asyncio
async def test_engine_streams_and_dedups(tmp_path, monkeypatch):
    monkeypatch.setenv("OFFICE_LAT", "12.97")
    monkeypatch.setenv("OFFICE_LNG", "80.18")
    cfg = EngineConfig(db_path=tmp_path / "t.db",
                       sources=[FakeSource()], deadline_s=10,
                       alert_fn=None)  # dry-run
    stats = await run_cycle(cfg)
    assert stats.raw_count == 3
    assert stats.after_dedup >= 1
```

- [ ] **Step 2: Confirm failure**

```bash
uv run pytest tests/pipeline/test_engine.py -v
```

- [ ] **Step 3: Implement engine (minimal — alert/enrich stubbed)**

```python
# src/core/engine.py
from __future__ import annotations
import asyncio, json, time, logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Awaitable
from src.core.circuit import Breaker, BreakerOpen
from src.core.http import AsyncHttp
from src.core.ratelimit import TokenBucket
from src.models import Listing, RunStats
from src.pipeline.dedup import fingerprint, merge
from src.sources.base import SourceAdapter, SourceCtx
from src.state.db import connect, migrate

logger = logging.getLogger("engine")


@dataclass
class EngineConfig:
    db_path: Path
    sources: list[SourceAdapter]
    deadline_s: float = 90
    alert_fn: Callable[[Listing, RunStats], Awaitable[int | None]] | None = None
    proxy: str | None = None


async def _run_source(source: SourceAdapter, ctx: SourceCtx,
                      out: asyncio.Queue, deadline: float, stats: RunStats) -> None:
    name = source.name
    stats.per_source[name] = {"scraped": 0, "kept": 0, "errored": 0, "ms": 0}
    t0 = time.monotonic()
    try:
        ctx.breaker.check()
        async with asyncio.timeout(deadline):
            async for listing in source.scrape(ctx):
                stats.per_source[name]["scraped"] += 1
                await out.put(listing)
        ctx.breaker.record_success()
    except BreakerOpen:
        stats.breaker_open.append(name)
        logger.warning("[%s] breaker open — skipped", name)
    except Exception as e:
        ctx.breaker.record_failure()
        stats.per_source[name]["errored"] += 1
        logger.exception("[%s] failed: %s", name, e)
    finally:
        stats.per_source[name]["ms"] = int((time.monotonic() - t0) * 1000)


async def run_cycle(cfg: EngineConfig) -> RunStats:
    stats = RunStats(started_at=int(time.time()))
    t0 = time.monotonic()
    queue: asyncio.Queue[Listing] = asyncio.Queue()
    fingerprints: dict[str, list[Listing]] = {}

    async with AsyncHttp(proxy=cfg.proxy) as http, \
               connect(cfg.db_path) as db:
        await migrate(db)
        ctxs = [
            SourceCtx(
                http=http,
                bucket=TokenBucket(s.rate.rate, s.rate.burst),
                breaker=Breaker(),
                logger=logger.getChild(s.name),
                config=None,
            ) for s in cfg.sources
        ]

        async def consume_and_dedup():
            while True:
                l = await queue.get()
                if l is None:
                    break
                fp = fingerprint(l)
                l = l.model_copy(update={"fingerprint": fp})
                fingerprints.setdefault(fp, []).append(l)
                stats.raw_count += 1

        consumer = asyncio.create_task(consume_and_dedup())

        async with asyncio.TaskGroup() as tg:
            for s, ctx in zip(cfg.sources, ctxs):
                tg.create_task(_run_source(s, ctx, queue, cfg.deadline_s, stats))

        await queue.put(None)
        await consumer

        deduped = [merge(group) for group in fingerprints.values()]
        stats.after_filter = stats.raw_count
        stats.after_dedup = len(deduped)

        if cfg.alert_fn:
            for l in deduped:
                msg_id = await cfg.alert_fn(l, stats)
                if msg_id is not None:
                    stats.alerted += 1

        stats.duration_ms = int((time.monotonic() - t0) * 1000)
        await db.execute(
            "INSERT INTO runs (started_at,duration_ms,raw_count,after_filter,"
            "after_dedup,alerted,per_source,breaker_open) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (stats.started_at, stats.duration_ms, stats.raw_count,
             stats.after_filter, stats.after_dedup, stats.alerted,
             json.dumps(stats.per_source), json.dumps(stats.breaker_open)))
        await db.commit()
    return stats
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/pipeline/test_engine.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add src/core/engine.py tests/pipeline/__init__.py tests/pipeline/test_engine.py
git commit -m "feat(core): async engine with dedup pipeline"
```

---

# Phase 3 — Migrate working scrapers (Sulekha, 99acres, SquareYards, CommonFloor, DuckDuckGo)

**Outcome:** All five currently-working scrapers ported to the new adapter contract with fixture-backed tests.

## Task 3.1: Adapter migration recipe (Sulekha — used as template)

**Files:**
- Create: `tests/fixtures/sulekha/pallavaram.html` (capture from `scripts/refresh_fixtures.py`)
- Create: `src/sources/sulekha.py`
- Create: `tests/adapter/test_sulekha.py`

- [ ] **Step 1: Create fixture-capture script**

```python
# scripts/refresh_fixtures.py
"""Usage: uv run python scripts/refresh_fixtures.py sulekha"""
import asyncio, sys
from pathlib import Path
from src.core.http import AsyncHttp

URLS = {
    "sulekha": [
        ("pallavaram",
         "https://property.sulekha.com/1-bhk-apartments-flats-for-rent/chennai/pallavaram"),
    ],
}


async def main(source: str):
    out = Path(f"tests/fixtures/{source}")
    out.mkdir(parents=True, exist_ok=True)
    async with AsyncHttp() as http:
        for name, url in URLS[source]:
            r = await http.get(url)
            (out / f"{name}.html").write_text(r.text, encoding="utf-8")
            print(f"saved {name}.html ({len(r.text)} chars)")

if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
```

- [ ] **Step 2: Capture the fixture**

```bash
uv run python scripts/refresh_fixtures.py sulekha
```

Expected: `tests/fixtures/sulekha/pallavaram.html` exists.

- [ ] **Step 3: Write failing adapter test**

```python
# tests/adapter/test_sulekha.py
import pytest, respx, httpx
from pathlib import Path
from src.sources.sulekha import Sulekha
from src.sources.base import SourceCtx
from src.core.http import AsyncHttp
from src.core.ratelimit import TokenBucket
from src.core.circuit import Breaker
import logging

FIXTURE = Path("tests/fixtures/sulekha/pallavaram.html").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_sulekha_parses_fixture(respx_mock):
    respx_mock.get(host="property.sulekha.com").mock(
        return_value=httpx.Response(200, text=FIXTURE))
    async with AsyncHttp() as http:
        ctx = SourceCtx(http=http, bucket=TokenBucket(100, 10), breaker=Breaker(),
                        logger=logging.getLogger("test"), config=None)
        listings = [l async for l in Sulekha().scrape(ctx)]
    assert len(listings) > 0
    assert all(l.source == "sulekha" for l in listings)
    assert all(l.price > 0 for l in listings)
```

- [ ] **Step 4: Confirm failure**

```bash
uv run pytest tests/adapter/test_sulekha.py -v
```

- [ ] **Step 5: Implement adapter (port logic from `src/scrapers/sulekha.py`)**

```python
# src/sources/sulekha.py
from __future__ import annotations
import json, re
from typing import AsyncIterator
from src.models import Listing
from src.sources.base import SourceAdapter, SourceCtx, RateLimit

_JSON_LD = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S)
_PRICE = re.compile(r"(?:Rent|₹|Rs\.?|INR)[^₹\d]{0,15}([\d,]{4,6})")
_ID = re.compile(r"-(\d{6,})-ad$")


class Sulekha(SourceAdapter):
    name = "sulekha"
    rate = RateLimit(rate=1.0, burst=3)

    def _urls(self, cfg) -> list[str]:
        from config import SEARCH_AREAS, CITY, PROPERTY_SLUG
        beds = PROPERTY_SLUG[0]
        city = CITY.lower()
        return [
            f"https://property.sulekha.com/{beds}-bhk-apartments-flats-for-rent/{city}/{a.lower().replace(' ', '-')}"
            for a in SEARCH_AREAS
        ]

    async def scrape(self, ctx: SourceCtx) -> AsyncIterator[Listing]:
        seen_ids: set[str] = set()
        for url in self._urls(ctx.config):
            ctx.breaker.check()
            await ctx.bucket.acquire()
            r = await ctx.http.get(url, headers={"Referer": "https://property.sulekha.com/"})
            if r.status_code not in (200, 206):
                continue
            for listing in self._parse(r.text):
                if listing.id in seen_ids: continue
                seen_ids.add(listing.id)
                yield listing

    def _parse(self, html: str) -> list[Listing]:
        from config import MIN_RENT, MAX_RENT, CITY
        out: list[Listing] = []
        for m in _JSON_LD.finditer(html):
            try:
                data = json.loads(m.group(1).strip())
            except json.JSONDecodeError:
                continue
            for item in (data if isinstance(data, list) else [data]):
                t = item.get("@type", [])
                if isinstance(t, str): t = [t]
                if not any(x in t for x in ("Apartment", "House", "Product")): continue
                url = item.get("url", "")
                if "sulekha" not in url: continue
                listing_id = (_ID.search(url) or [None, url[-12:]])[1]
                offers = item.get("offers") or {}
                price = None
                if isinstance(offers, dict):
                    p = offers.get("price") or offers.get("lowPrice")
                    if p:
                        try: price = int(str(p).replace(",", ""))
                        except ValueError: pass
                if not price:
                    pm = _PRICE.search(item.get("description", "") + item.get("name", ""))
                    if pm: price = int(pm.group(1).replace(",", ""))
                if not price or not (MIN_RENT <= price <= MAX_RENT): continue
                geo = item.get("geo") or {}
                try:
                    lat = float(geo.get("latitude") or 0) or None
                    lng = float(geo.get("longitude") or 0) or None
                except (ValueError, TypeError):
                    lat = lng = None
                address = str(item.get("address") or "")
                if CITY.lower() not in address.lower():
                    address = f"{address}, {CITY}".strip(", ")
                out.append(Listing(
                    id=f"sulekha_{listing_id}", source="sulekha",
                    title=str(item.get("name") or "1 BHK")[:120],
                    address=address, price=price, url=url,
                    lat=lat, lng=lng,
                ))
        return out
```

- [ ] **Step 6: Run tests**

```bash
uv run pytest tests/adapter/test_sulekha.py -v
```

Expected: 1 passed.

- [ ] **Step 7: Commit**

```bash
git add scripts/refresh_fixtures.py src/sources/sulekha.py tests/adapter/__init__.py tests/adapter/test_sulekha.py tests/fixtures/sulekha/pallavaram.html
git commit -m "feat(sources): port Sulekha adapter"
```

## Task 3.2: SquareYards adapter

Same recipe as 3.1. Reference logic in `src/scrapers/squareyards.py`. Capture fixture, write test, port `_parse` into `Sulekha`-style class.

- [ ] Add `squareyards` to `URLS` in `scripts/refresh_fixtures.py` with one search URL.
- [ ] Capture fixture: `uv run python scripts/refresh_fixtures.py squareyards`
- [ ] Write `tests/adapter/test_squareyards.py` (same shape as Sulekha test).
- [ ] Confirm test fails.
- [ ] Implement `src/sources/squareyards.py` — JSON-LD parser, same structure as `Sulekha`.
- [ ] Run test, confirm pass.
- [ ] Commit: `feat(sources): port SquareYards adapter`.

## Task 3.3: CommonFloor adapter

Same recipe. Reference `src/scrapers/commonfloor.py`. CommonFloor uses a `__STATE_FROM_SERVER__` JSON blob — port that regex extraction.

- [ ] Update `scripts/refresh_fixtures.py`, capture fixture.
- [ ] `tests/adapter/test_commonfloor.py`.
- [ ] `src/sources/commonfloor.py`.
- [ ] Test → commit: `feat(sources): port CommonFloor adapter`.

## Task 3.4: 99acres adapter (with `__NEXT_DATA__` fast path)

**Files:**
- Create: `src/sources/ninetynine_acres.py`
- Create: `tests/adapter/test_ninetynine_acres.py`

- [ ] **Step 1: Update refresh_fixtures.py** to include a 99acres search URL.

- [ ] **Step 2: Capture fixture**

```bash
uv run python scripts/refresh_fixtures.py ninetynine_acres
```

- [ ] **Step 3: Inspect captured HTML** — verify it contains `__NEXT_DATA__`:

```bash
uv run python -c "from pathlib import Path; html = Path('tests/fixtures/ninetynine_acres/pallavaram.html').read_text(encoding='utf-8'); print('__NEXT_DATA__' in html)"
```

If `True`: implement the fast path (no Playwright). If `False`: fall back to porting the Playwright logic from `src/scrapers/acres99.py`, mark `needs_browser = True`.

- [ ] **Step 4: Write failing test** (mirror Sulekha shape).

- [ ] **Step 5: Implement `src/sources/ninetynine_acres.py`** — extract `__NEXT_DATA__` JSON, walk the listing array. Skeleton:

```python
import json, re
from typing import AsyncIterator
from src.models import Listing
from src.sources.base import SourceAdapter, SourceCtx, RateLimit

_NEXT_DATA = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


class NinetyNineAcres(SourceAdapter):
    name = "99acres"
    rate = RateLimit(rate=0.5, burst=2)
    needs_browser = False  # toggle to True if Next data isn't present

    async def scrape(self, ctx: SourceCtx) -> AsyncIterator[Listing]:
        # iterate config.SEARCH_AREAS → build URLs → fetch → _parse
        ...

    def _parse(self, html: str) -> list[Listing]:
        m = _NEXT_DATA.search(html)
        if not m: return []
        data = json.loads(m.group(1))
        # walk data["props"]["pageProps"]["searchResults"] or similar
        # actual path verified during fixture inspection in step 3
        ...
```

- [ ] **Step 6: Run test, commit.**

## Task 3.5: DuckDuckGo adapter

Port `src/scrapers/duckduckgo.py` as a "meta-discovery" adapter. Lower priority since it surfaces existing-source URLs.

- [ ] Capture fixture (DDG HTML result for a query).
- [ ] Write `tests/adapter/test_duckduckgo.py`.
- [ ] Implement `src/sources/duckduckgo.py` — extract NoBroker URLs from result links, return as low-priority `Listing`s with `source="duckduckgo"`.
- [ ] Commit: `feat(sources): port DuckDuckGo discovery adapter`.

---

# Phase 4 — Resurrect blocked scrapers (NoBroker, MagicBricks, Housing, OLX)

**Outcome:** Four formerly-blocked sources return real listings using their own JSON/`__NEXT_DATA__` endpoints. Each in its own PR with fixture.

> **For each task below:** first capture a fixture via DevTools network tab (manually inspect what the site's frontend calls), save to `tests/fixtures/<source>/`, then implement against the fixture. **Never** ship code that hits a live site in tests.

## Task 4.1: NoBroker via public JSON endpoint

**Files:**
- Create: `tests/fixtures/nobroker/pallavaram.json`
- Create: `src/sources/nobroker.py`
- Create: `tests/adapter/test_nobroker.py`

- [ ] **Step 1: Discover endpoint** — open https://www.nobroker.in in DevTools → Network → set city/area filters → identify the XHR request returning listing JSON (URL pattern observed in spec phase: `/api/v1/property/filter/`). Save its query params and full JSON response to `tests/fixtures/nobroker/pallavaram.json`.

- [ ] **Step 2: Write failing test against the fixture**

```python
# tests/adapter/test_nobroker.py
import json, pytest, httpx
from pathlib import Path
from src.sources.nobroker import NoBroker
from src.sources.base import SourceCtx
from src.core.http import AsyncHttp
from src.core.ratelimit import TokenBucket
from src.core.circuit import Breaker
import logging

PAYLOAD = json.loads(Path("tests/fixtures/nobroker/pallavaram.json").read_text())


@pytest.mark.asyncio
async def test_nobroker_parses(respx_mock):
    respx_mock.get(host="www.nobroker.in").mock(
        return_value=httpx.Response(200, json=PAYLOAD))
    async with AsyncHttp() as http:
        ctx = SourceCtx(http=http, bucket=TokenBucket(100, 10), breaker=Breaker(),
                        logger=logging.getLogger("test"), config=None)
        listings = [l async for l in NoBroker().scrape(ctx)]
    assert listings
    assert all(l.source == "nobroker" for l in listings)
```

- [ ] **Step 3: Implement.** The exact JSON shape is determined by your fixture. Skeleton:

```python
# src/sources/nobroker.py
from typing import AsyncIterator
from src.models import Listing
from src.sources.base import SourceAdapter, SourceCtx, RateLimit


class NoBroker(SourceAdapter):
    name = "nobroker"
    rate = RateLimit(rate=0.5, burst=2)

    async def scrape(self, ctx: SourceCtx) -> AsyncIterator[Listing]:
        # build the same params your fixture used; iterate SEARCH_AREAS
        for params in self._param_sets(ctx.config):
            ctx.breaker.check()
            await ctx.bucket.acquire()
            r = await ctx.http.get(
                "https://www.nobroker.in/api/v1/property/filter/",
                params=params,
                headers={"Accept": "application/json",
                         "Referer": "https://www.nobroker.in/"},
            )
            if r.status_code != 200: continue
            payload = r.json()
            for item in payload.get("data", []):
                yield self._to_listing(item)
            ...
```

- [ ] **Step 4: Run test, iterate parse to match fixture.**

- [ ] **Step 5: Commit:** `feat(sources): NoBroker via public JSON endpoint`.

## Task 4.2: MagicBricks via curl_cffi + `__NEXT_DATA__`

- [ ] Use `curl_cffi` AsyncSession with `impersonate="chrome110"` (extend `src/core/http.py` to expose a `cffi_get(url)` method, or import directly inside the adapter).
- [ ] Capture fixture: open `https://www.magicbricks.com/property-for-rent/...` in a fresh browser, save HTML.
- [ ] Verify `__NEXT_DATA__` script tag present.
- [ ] Write test + adapter, parsing the `pageProps.searchData.listings` array.
- [ ] Commit: `feat(sources): MagicBricks via __NEXT_DATA__`.

## Task 4.3: Housing.com via fixed Accept header + `__NEXT_DATA__`

- [ ] Adapter sets `Accept: text/html,application/xhtml+xml;q=0.9,*/*;q=0.8` to bypass the 406.
- [ ] Capture fixture, write test, implement using `__NEXT_DATA__` extraction.
- [ ] Commit: `feat(sources): Housing.com via fixed headers`.

## Task 4.4: OLX via internal REST API

- [ ] DevTools-capture the OLX search XHR (observed pattern `/api/relevance/v4/search`). Save fixture JSON.
- [ ] Write test + adapter — parse `data` array.
- [ ] Commit: `feat(sources): OLX via REST API`.

## Task 4.5: Wire all sources into the engine

**Files:**
- Modify: `src/core/engine.py` (or new `src/sources/registry.py`)

- [ ] Create `src/sources/registry.py`:

```python
from src.sources.sulekha import Sulekha
from src.sources.squareyards import SquareYards
from src.sources.commonfloor import CommonFloor
from src.sources.ninetynine_acres import NinetyNineAcres
from src.sources.duckduckgo import DuckDuckGo
from src.sources.nobroker import NoBroker
from src.sources.magicbricks import MagicBricks
from src.sources.housing import Housing
from src.sources.olx import OLX

ALL_SOURCES = [Sulekha, SquareYards, CommonFloor, NinetyNineAcres,
               DuckDuckGo, NoBroker, MagicBricks, Housing, OLX]
```

- [ ] Add a `tests/pipeline/test_engine_full.py` that instantiates all 9 with mocked HTTP and asserts the engine handles ≥ 1 source crash without aborting.
- [ ] Commit: `feat(sources): registry of all 9 adapters`.

---

# Phase 5 — Switch entry points + tracker bot + digest

**Outcome:** `run_once.py` and `monitor.py` drive the new engine. Old `src/scrapers/*` and `src/scheduler.py` live under `legacy/` for one week. Daily digest workflow added.

## Task 5.1: Property + distance filter + travel-time enrich into pipeline

**Files:**
- Create: `src/pipeline/enrich.py`
- Modify: `src/core/engine.py` to call enrich

- [ ] Port the existing `src/filters/property_filter.py` and `src/filters/distance_filter.py` as pure functions. Reuse `src/travel_time.py` unchanged but call via a thin async wrapper (`asyncio.to_thread`).
- [ ] Add unit tests for property + distance filter using `Listing` objects.
- [ ] Add `pipeline.enrich.attach_commute(listing, conn) -> tuple[Listing, int | None]` that hits the cached travel time.
- [ ] Wire `engine.run_cycle` to call the pipeline in order:
  1. `property_filter` — drop wrong bedrooms / out-of-budget
  2. `distance_filter` — drop > MAX_RADIUS_KM from office
  3. `dedup.merge` — collapse fingerprint groups (already in engine from Task 2.8)
  4. `enrich.attach_commute` — only for survivors
  5. `rank.fit_score` — sort descending
  6. **`seen_filter`** — for each candidate, `SELECT alerted_at FROM listings WHERE fingerprint = ?`. If row exists and `alerted_at IS NOT NULL`, skip (already alerted). Otherwise UPSERT the row and proceed to alert.
  7. `alert_fn` — send via Telegram; on success write `alerted_at = now, msg_id = ?` back to `listings`.
- [ ] Commit: `feat(pipeline): filter + enrich integration`.

## Task 5.2: Alert function — wrap existing `notifier/tracker_bot.py`

**Files:**
- Create: `src/notifier/alert_v2.py`
- Modify: `src/core/engine.py` to accept it

- [ ] Build the alert function:

```python
# src/notifier/alert_v2.py
import asyncio, hashlib
from src.models import Listing
from src.notifier.tracker_bot import send_with_buttons

async def alert(listing: Listing, _stats) -> int | None:
    tracking_id = hashlib.sha256(
        (listing.fingerprint or listing.url).encode()).hexdigest()[:16]
    # call into existing sync tracker bot via thread
    return await asyncio.to_thread(_send, listing, tracking_id)

def _send(listing: Listing, tracking_id: str) -> int | None:
    from monitor import _format_alert  # reuse existing formatter
    msg = _format_alert(listing, None, None, None, "engine")
    return send_with_buttons(msg, tracking_id)
```

- [ ] Add `tests/unit/test_alert_v2.py` with `_send` mocked.
- [ ] Commit: `feat(notifier): v2 alert wrapper`.

## Task 5.3: Cutover seed script

**Files:**
- Create: `scripts/seed_v2_seen.py`

- [ ] Script reads the legacy `seen` rows from the existing DB (in the `solo` namespace) and inserts equivalent `listings` rows so the first v2 cycle doesn't re-alert old items.
- [ ] Document usage in `README.md`.
- [ ] Commit: `chore: cutover seed script`.

## Task 5.4: Switch run_once.py + monitor.py

**Files:**
- Modify: `run_once.py`, `monitor.py`
- Move: `src/scheduler.py` → `legacy/scheduler.py`; `src/scrapers/` → `legacy/scrapers/`

- [ ] Modify `run_once.py`:

```python
import asyncio, os
from pathlib import Path
from dotenv import load_dotenv
from src.core.engine import run_cycle, EngineConfig
from src.sources.registry import ALL_SOURCES
from src.notifier.alert_v2 import alert

load_dotenv()


def main():
    if "--digest" in os.sys.argv:
        from src.notifier.digest import run_digest
        return asyncio.run(run_digest(Path(os.environ.get("DB_PATH", "data/rental_monitor.db"))))
    cfg = EngineConfig(
        db_path=Path(os.environ.get("DB_PATH", "data/rental_monitor.db")),
        sources=[S() for S in ALL_SOURCES],
        deadline_s=90,
        alert_fn=alert,
        proxy=os.environ.get("PROXY_URL"),
    )
    asyncio.run(run_cycle(cfg))


if __name__ == "__main__":
    main()
```

- [ ] Modify `monitor.py` to be a thin loop around `run_once.main()` every `CHECK_INTERVAL_SECONDS`.
- [ ] Move legacy code: `git mv src/scheduler.py legacy/scheduler.py && git mv src/scrapers legacy/scrapers && git mv src/db.py legacy/db.py`
- [ ] Run the full test suite:

```bash
uv run pytest -v
```

Expected: all green.

- [ ] **Smoke-test locally** with real Telegram secrets:

```bash
DB_PATH=data/test.db uv run python run_once.py
```

Watch Telegram for fresh alerts; confirm cycle ≤ 90 s.

- [ ] Commit: `feat: switch entry points to v2 engine; legacy quarantined`.

## Task 5.5: Pending-alerts processor + prune policy

**Files:**
- Modify: `src/core/engine.py`
- Create: `tests/pipeline/test_prune.py`

- [ ] **Step 1: Add `process_pending(conn)` at the start of `run_cycle`** — read up to N rows from `pending_alerts`, attempt to re-send via `alert_fn`. On success delete the row; on failure increment `retry_count`; drop rows where `retry_count >= 48`.

- [ ] **Step 2: Add `prune(conn, now_ts)` at end of `run_cycle`** matching spec Section 5:

```python
async def prune(conn, now_ts: int) -> None:
    SIXTY_D = 60 * 86400
    ONE_EIGHTY_D = 180 * 86400
    THIRTY_D = 30 * 86400
    await conn.execute(
        "DELETE FROM listings WHERE last_seen < ? AND alerted_at IS NULL",
        (now_ts - SIXTY_D,))
    await conn.execute(
        "DELETE FROM listings WHERE last_seen < ?",
        (now_ts - ONE_EIGHTY_D,))
    await conn.execute(
        "DELETE FROM runs WHERE run_id NOT IN "
        "(SELECT run_id FROM runs ORDER BY run_id DESC LIMIT 100)")
    await conn.execute(
        "DELETE FROM travel_cache WHERE cached_at < ?", (now_ts - THIRTY_D,))
    await conn.commit()
    size = (await (await conn.execute(
        "SELECT page_count*page_size FROM pragma_page_count, pragma_page_size")
    ).fetchone())[0]
    if size > 5 * 1024 * 1024:
        await conn.execute("VACUUM")
```

- [ ] **Step 3: Write test** that seeds old `listings`/`runs`/`travel_cache` rows and asserts prune deletes the right ones; seeds 5 stale `pending_alerts` (retry_count=49) and asserts they're dropped.

- [ ] **Step 4: Run tests, commit:** `feat(engine): pending-alerts retry + prune policy`.

## Task 5.6: Daily digest

**Files:**
- Create: `src/notifier/digest.py`
- Create: `.github/workflows/digest.yml`

- [ ] Implement `run_digest(db_path)`:
  - Top 5 listings of last 24 h by fit score (read from `listings` + `runs`)
  - Per-source health summary (✅/⚠️/❌ based on last 24 cycles)
  - **Silent-source detector** (spec Section 6): for each source, count cycles in the last 3 hours where `per_source[source].scraped == 0`. If ≥ 3, append `⚠️ <source> has been silent 3h — may be blocked` to the digest body.
  - Format as one Telegram message and post.
- [ ] Create workflow `.github/workflows/digest.yml`:

```yaml
name: Daily Digest
on:
  schedule:
    - cron: '30 3 * * *'  # 09:00 IST
  workflow_dispatch:
concurrency:
  group: rental-monitor
  cancel-in-progress: false
jobs:
  digest:
    runs-on: ubuntu-latest
    timeout-minutes: 3
    permissions: { contents: read }
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync
      - name: Restore state
        run: |
          git fetch origin state || true
          git checkout origin/state -- data/rental_monitor.db || true
      - name: Digest
        env:
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          DB_PATH: data/rental_monitor.db
        run: uv run python run_once.py --digest
```

- [ ] Commit: `feat(digest): daily Telegram summary workflow`.

---

# Phase 6 — Cleanup, README, tag

**Outcome:** Legacy gone, README reflects v2, `v2.0.0` tag.

## Task 5.7: Daily digest workflow file

(moved from Task 5.5 — same content as the GH workflow yaml above)

## Task 6.1: Delete legacy after one week of stable runs

- [ ] After one full week of green CI on `upgrade/v2`, delete:

```bash
git rm -r legacy/
```

- [ ] Commit: `chore: drop legacy scrapers and scheduler`.

## Task 6.2: Update README

- [ ] Rewrite Project Structure section to match new layout.
- [ ] Document `LLM_API_KEY` and `PROXY_URL` optional env vars + their graceful-degrade behaviour.
- [ ] Document the `state` branch convention (don't manually push to it).
- [ ] Commit: `docs: update README for v2`.

## Task 6.3: Tag and PR to main

- [ ] Open PR `upgrade/v2 → main`. Body links to the spec and lists per-phase commits.
- [ ] After merge:

```bash
git checkout main && git pull
git tag -a v2.0.0 -m "v2: async rewrite"
git push origin v2.0.0
```

- [ ] Update `MEMORY.md` `project_rental_monitor.md` to reflect v2.

---

## Out of scope (reaffirmed)

- Web dashboard (`runs` table is queryable directly — defer until needed)
- Push/webhook architecture (hourly cron remains)
- New source portals beyond the existing nine
- Multi-user / SaaS form factor
- Auto-contact / auto-viewing booking automation

## Deferred to follow-up plan (intentionally not in v2.0.0)

- **Optional LLM layer** (spec Section 4) — env vars `LLM_API_KEY` are plumbed through workflows and `EngineConfig` but the three batched calls (address canonicalization, spam detection, personalised re-rank) are deferred to a v2.1 plan. The engine code path is identical with or without the key; when key is absent the layer is a no-op.
- **Sitemap-based discovery** for MagicBricks/Housing — Phase 4 adapters use `__NEXT_DATA__` directly; sitemap mining can be added later if those break.
- **Image-hash dedup** as a secondary signal — geohash+price fingerprint is enough for v2.

## Cross-cutting reminders

- **Each task ends in a green commit.** Never leave a step half-done across commits.
- **Use `uv run pytest -v`** before every commit — refuse to commit on red.
- **Fixtures live in git** so tests are reproducible without network.
- **Never** run the live `smoke` marker in CI; it's local-only.
- **Politeness** is non-negotiable — don't lower rate limits to "speed up" individual sources.

---

## References

- Spec: `docs/superpowers/specs/2026-05-29-rental-monitor-upgrade-design.md`
- Memory: `~/.claude/projects/C--Users-harsh/memory/project_rental_monitor.md`
- Legacy code (for porting reference until Phase 6): `src/scrapers/`, `src/scheduler.py`, `src/db.py`
