"""Cutover seed: copy legacy ``seen_listings`` rows into v2 ``listings``.

Usage::

    uv run python scripts/seed_v2_seen.py /path/to/legacy.db /path/to/v2.db

The v2 fingerprint is geohash+price+bedrooms+furnishing, which we can't
reconstruct from a bare ``(id, source)`` row. Instead we synthesise a
deterministic ``legacy_<source>_<id>`` fingerprint and mark the row as
already alerted. This preserves history (Telegram dedup, /summary
listing-tracker links still work via tracking_id) without guaranteeing
that the first v2 cycle won't re-alert an item that genuinely matches
under the new schema.

In practice: most legacy listings are no longer live (the seen table
accumulates over months) and the few that are still live will re-alert
once. That's the accepted tradeoff for the schema upgrade.
"""
from __future__ import annotations
import asyncio
import json
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

import aiosqlite

from src.state.db import connect, migrate


def _ts(s: str) -> int:
    try:
        return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())
    except Exception:
        return int(time.time())


async def _seed(legacy_db: Path, v2_db: Path) -> int:
    legacy = sqlite3.connect(legacy_db)
    rows = legacy.execute(
        "SELECT id, source, seen_at FROM seen_listings").fetchall()
    legacy.close()
    if not rows:
        return 0

    async with connect(v2_db) as db:
        await migrate(db)
        for (listing_id, source, seen_at) in rows:
            fp = f"legacy_{source}_{listing_id}"
            ts = _ts(seen_at)
            canonical = json.dumps({"id": listing_id, "source": source,
                                    "legacy": True})
            await db.execute(
                "INSERT OR IGNORE INTO listings "
                "(fingerprint, first_seen, last_seen, sources, canonical, alerted_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (fp, ts, ts, json.dumps([source]), canonical, ts))
        await db.commit()
    return len(rows)


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: seed_v2_seen.py <legacy_db> <v2_db>", file=sys.stderr)
        return 2
    legacy_db = Path(sys.argv[1])
    v2_db = Path(sys.argv[2])
    n = asyncio.run(_seed(legacy_db, v2_db))
    print(f"seeded {n} legacy listings into {v2_db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
