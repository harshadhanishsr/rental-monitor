"""Post-scrape pipeline stages: property filter, distance filter, commute,
seen-filter, listings upsert.

All stages take a :class:`Listing` and return new values (no mutation).
"""
from __future__ import annotations
import asyncio
import json
import re
import time

import aiosqlite
from haversine import Unit, haversine

from src.models import Listing

_FAMILIES_ONLY = re.compile(r"famil(y|ies)\s*only", re.IGNORECASE)
_BACHELOR_KEYWORDS = re.compile(r"\b(bachelor|single|bachelors)\b", re.IGNORECASE)


def passes_property_filter(l: Listing) -> bool:
    """Budget + bachelor + furnishing checks. Bedroom is handled by adapters."""
    from config import FURNISHING, MAX_RENT, MIN_RENT, NUM_PEOPLE
    if l.price > MAX_RENT or l.price < MIN_RENT:
        return False
    if _FAMILIES_ONLY.search(l.title) and NUM_PEOPLE < 3:
        return False
    bachelors_allowed = l.bachelors_allowed
    if bachelors_allowed is None and _BACHELOR_KEYWORDS.search(l.title):
        bachelors_allowed = True
    if NUM_PEOPLE == 1 and bachelors_allowed is False:
        return False
    if FURNISHING != "any":
        text = (l.title + " " + (l.furnishing or "")).lower()
        wanted = "semi" if FURNISHING == "semi-furnished" else FURNISHING
        if wanted not in text:
            return False
    return True


def passes_distance_filter(
    l: Listing, office_lat: float, office_lng: float, max_km: float,
) -> tuple[bool, float | None]:
    """Return ``(passes, distance_km)``. Listings without coords are dropped
    here — the geohash fingerprint already relied on lat/lng for accurate
    cross-source dedup, so callers should ensure adapters fill those in."""
    if l.lat is None or l.lng is None:
        return False, None
    dist = haversine((office_lat, office_lng), (l.lat, l.lng), unit=Unit.KILOMETERS)
    return (dist <= max_km), dist


def is_priority(l: Listing) -> bool:
    from config import PRIORITY_LOCALITIES
    addr = l.address.lower()
    return any(p in addr for p in PRIORITY_LOCALITIES)


async def attach_commute(l: Listing, conn: aiosqlite.Connection) -> int | None:
    """Return cached travel-minutes to ``OFFICE_*`` or compute via heuristic.

    For network-free pipelines (tests, CI without API keys), the heuristic
    falls back to ``distance_km * 1.25 / 28 km/h``. Results are persisted to
    ``travel_cache`` for the next cycle."""
    from config import OFFICE_LAT, OFFICE_LNG
    if l.lat is None or l.lng is None:
        return None
    key = f"{OFFICE_LAT:.4f},{OFFICE_LNG:.4f}|{l.lat:.4f},{l.lng:.4f}|driving"
    row = await (await conn.execute(
        "SELECT minutes FROM travel_cache WHERE cache_key = ?", (key,))).fetchone()
    if row is not None:
        return int(round(row[0]))
    # No external HTTP here — keep the pipeline deterministic; richer travel
    # estimation lives in ``src/travel_time.py`` and can be wired via
    # asyncio.to_thread when API keys are present.
    dist = haversine((OFFICE_LAT, OFFICE_LNG), (l.lat, l.lng), unit=Unit.KILOMETERS)
    minutes = round(dist * 1.25 / 28 * 60, 1)
    await conn.execute(
        "INSERT OR REPLACE INTO travel_cache (cache_key, minutes, source, cached_at) "
        "VALUES (?, ?, ?, ?)",
        (key, minutes, "heuristic", int(time.time())))
    return int(round(minutes))


async def upsert_listing(
    conn: aiosqlite.Connection, l: Listing, now_ts: int,
) -> tuple[int, int]:
    """Insert or refresh the listings row keyed by ``fingerprint``.

    Returns ``(first_seen_ts, confirm_count)`` where confirm_count is the
    number of distinct sources that have ever reported this fingerprint."""
    assert l.fingerprint, "fingerprint must be set before upsert"
    row = await (await conn.execute(
        "SELECT first_seen, sources FROM listings WHERE fingerprint = ?",
        (l.fingerprint,))).fetchone()
    sources_now = {l.source, *(l.also_seen_on or [])}
    if row is None:
        first_seen = now_ts
        sources = sources_now
    else:
        first_seen = row[0]
        try:
            existing = set(json.loads(row[1]))
        except (TypeError, json.JSONDecodeError):
            existing = set()
        sources = existing | sources_now
    canonical = l.model_dump_json()
    await conn.execute(
        "INSERT INTO listings (fingerprint, first_seen, last_seen, sources, canonical) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(fingerprint) DO UPDATE SET "
        "  last_seen = excluded.last_seen, "
        "  sources   = excluded.sources, "
        "  canonical = excluded.canonical",
        (l.fingerprint, first_seen, now_ts, json.dumps(sorted(sources)), canonical))
    return first_seen, len(sources)


async def already_alerted(conn: aiosqlite.Connection, fingerprint: str) -> bool:
    row = await (await conn.execute(
        "SELECT alerted_at FROM listings WHERE fingerprint = ?",
        (fingerprint,))).fetchone()
    return bool(row and row[0] is not None)


async def mark_alerted(
    conn: aiosqlite.Connection, fingerprint: str, msg_id: int, now_ts: int,
) -> None:
    await conn.execute(
        "UPDATE listings SET alerted_at = ?, msg_id = ? WHERE fingerprint = ?",
        (now_ts, msg_id, fingerprint))
