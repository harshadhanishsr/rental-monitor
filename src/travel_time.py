"""
Travel time estimation between two coordinates.

Strategy (in priority order):
1. Ola Maps API  — primary source for driving + transit in India.
                   Knows Chennai MTC bus routes, MRTS, metro, real traffic.
2. OpenRouteService — used for walking legs (to/from transit stops).
                   Combined with Ola Maps transit for door-to-door accuracy.
3. Heuristic     — straight-line distance × mode speed. Used when both APIs
                   are unavailable or fail. Results marked with ~ in alerts.

Setup (both free, no credit card):
  Ola Maps:  https://maps.olacabs.com/api  →  OLA_MAPS_API_KEY in .env
  ORS:       https://openrouteservice.org  →  ORS_API_KEY in .env
"""
import hashlib
import json
import logging
import os
import sqlite3
import time
import requests
from haversine import haversine, Unit

logger = logging.getLogger(__name__)

# ── API endpoints ─────────────────────────────────────────────
OLA_DIRECTIONS_URL = "https://api.olamaps.io/routing/v1/directions"
ORS_DIRECTIONS_URL = "https://api.openrouteservice.org/v2/directions/{profile}/json"

# ── Speed heuristics (km/h, Indian city conditions) ───────────
_SPEED = {
    "driving":     28,
    "two_wheeler": 25,
    "transit":     18,   # bus + walk overhead
    "company_cab": 30,
    "walking":     5,
}

# ── Ola Maps mode mapping ─────────────────────────────────────
_OLA_MODE = {
    "driving":     "driving",
    "two_wheeler": "driving",
    "transit":     "transit",
    "company_cab": "driving",
    "walking":     "walking",
}

# ── ORS profile mapping ───────────────────────────────────────
_ORS_PROFILE = {
    "driving":     "driving-car",
    "two_wheeler": "driving-car",
    "walking":     "foot-walking",
    "transit":     "foot-walking",   # ORS used only for walking legs in transit
}


def _ola_key() -> str:
    return os.environ.get("OLA_MAPS_API_KEY", "")


def _ors_key() -> str:
    return os.environ.get("ORS_API_KEY", "")


# ── SQLite cache ──────────────────────────────────────────────

def _init_cache(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS travel_time_cache (
            cache_key   TEXT PRIMARY KEY,
            minutes     REAL,
            walk_minutes REAL,
            source      TEXT,
            created_at  INTEGER DEFAULT (strftime('%s','now'))
        )
    """)
    conn.commit()


def _cache_key(olat, olng, dlat, dlng, mode: str) -> str:
    s = f"{olat:.4f},{olng:.4f}|{dlat:.4f},{dlng:.4f}|{mode}"
    return hashlib.sha256(s.encode()).hexdigest()[:20]


def _get_cached(conn: sqlite3.Connection, key: str):
    row = conn.execute(
        "SELECT minutes, walk_minutes, source FROM travel_time_cache WHERE cache_key = ?",
        (key,)
    ).fetchone()
    return row if row else None


def _set_cached(conn, key, minutes, walk_minutes, source):
    conn.execute(
        "INSERT OR REPLACE INTO travel_time_cache "
        "(cache_key, minutes, walk_minutes, source) VALUES (?, ?, ?, ?)",
        (key, minutes, walk_minutes, source),
    )
    conn.commit()


# ── Heuristic fallback ────────────────────────────────────────

def _heuristic_minutes(dist_km: float, mode: str) -> float:
    """Estimate travel time. Road distance ≈ straight-line × 1.25."""
    speed = _SPEED.get(mode, 20)
    return round(dist_km * 1.25 / speed * 60, 1)


# ── Ola Maps ──────────────────────────────────────────────────

def _ola_minutes(olat, olng, dlat, dlng, mode: str) -> float | None:
    """Query Ola Maps Directions API. Returns minutes or None on failure."""
    key = _ola_key()
    if not key:
        return None
    ola_mode = _OLA_MODE.get(mode, "driving")
    params = {
        "origin":      f"{olat},{olng}",
        "destination": f"{dlat},{dlng}",
        "mode":        ola_mode,
        "api_key":     key,
    }
    try:
        r = requests.get(OLA_DIRECTIONS_URL, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        if data.get("status") != "OK" or not data.get("routes"):
            logger.warning("Ola Maps: status=%s mode=%s", data.get("status"), mode)
            return None
        leg = data["routes"][0]["legs"][0]
        # duration_in_traffic preferred for driving; duration for transit/walking
        duration = leg.get("duration_in_traffic") or leg.get("duration")
        if isinstance(duration, dict):
            secs = duration.get("value", 0)
        else:
            secs = int(duration or 0)
        return round(secs / 60, 1)
    except Exception:
        logger.exception("Ola Maps API failed for mode=%s", mode)
        return None


# ── OpenRouteService ─────────────────────────────────────────

def _ors_minutes(olat, olng, dlat, dlng, mode: str) -> float | None:
    """Query OpenRouteService. Returns minutes or None on failure."""
    key = _ors_key()
    if not key:
        return None
    profile = _ORS_PROFILE.get(mode, "foot-walking")
    url = ORS_DIRECTIONS_URL.format(profile=profile)
    headers = {
        "Authorization": key,
        "Content-Type":  "application/json",
    }
    body = {
        "coordinates": [[olng, olat], [dlng, dlat]],  # ORS uses [lng, lat]
        "units": "km",
    }
    try:
        r = requests.post(url, headers=headers, json=body, timeout=10)
        r.raise_for_status()
        data = r.json()
        secs = data["routes"][0]["summary"]["duration"]
        return round(secs / 60, 1)
    except Exception:
        logger.exception("ORS API failed for mode=%s", mode)
        return None


# ── Main entry point ─────────────────────────────────────────

def get_travel_time(
    olat: float, olng: float,
    dlat: float, dlng: float,
    mode: str,
    conn: sqlite3.Connection,
) -> tuple[float, str, float | None]:
    """
    Returns (total_minutes, source, walk_minutes).

    For transit: total_minutes = Ola Maps door-to-door transit time.
                 walk_minutes  = ORS walking time (supplement — how long
                                 if you had to walk the whole way).
    source: "ola", "ola+ors", "ors", "heuristic", "cached"
    walk_minutes is None for non-transit modes.
    """
    _init_cache(conn)
    key = _cache_key(olat, olng, dlat, dlng, mode)
    cached = _get_cached(conn, key)
    if cached:
        return cached[0], "cached", cached[1]

    walk_minutes = None
    source = "heuristic"
    minutes = None

    # ── Transit: Ola Maps (door-to-door) + ORS walking supplement
    if mode == "transit":
        minutes = _ola_minutes(olat, olng, dlat, dlng, "transit")
        if minutes:
            source = "ola"
        # Always get walking time via ORS as a reference
        walk_minutes = _ors_minutes(olat, olng, dlat, dlng, "walking")
        if walk_minutes and minutes:
            source = "ola+ors"

    # ── Driving / two_wheeler: Ola Maps
    elif mode in ("driving", "two_wheeler", "company_cab"):
        minutes = _ola_minutes(olat, olng, dlat, dlng, mode)
        if minutes:
            source = "ola"
        else:
            # ORS fallback for driving
            minutes = _ors_minutes(olat, olng, dlat, dlng, mode)
            if minutes:
                source = "ors"

    # ── Walking: ORS
    elif mode == "walking":
        minutes = _ors_minutes(olat, olng, dlat, dlng, "walking")
        if minutes:
            source = "ors"
        walk_minutes = minutes

    # ── Heuristic fallback
    if minutes is None:
        dist_km = haversine((olat, olng), (dlat, dlng), unit=Unit.KILOMETERS)
        minutes = _heuristic_minutes(dist_km, mode)
        source = "heuristic"
        if mode == "transit" and walk_minutes is None:
            walk_minutes = _heuristic_minutes(dist_km, "walking")

    _set_cached(conn, key, minutes, walk_minutes, source)
    return minutes, source, walk_minutes
