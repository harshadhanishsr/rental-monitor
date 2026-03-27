"""
Travel time estimation between two coordinates.

Priority:
1. Google Maps Distance Matrix API (most accurate — real traffic, real transit routes)
2. Heuristic estimate based on straight-line distance + transport mode
   (used when no API key is set or the API call fails)

Caches results in SQLite so the same origin→destination pair is never
queried twice, keeping API usage within the free tier.
"""
import hashlib
import logging
import os
import sqlite3
import time
import requests
from haversine import haversine, Unit

logger = logging.getLogger(__name__)

# ── Speed heuristics (city conditions, India) ─────────────────
# Used when Google Maps API is not configured.
# Values in km/h; travel_minutes = distance_km / speed * 60
_HEURISTIC_SPEED_KMH = {
    "driving":     28,   # city traffic, car/auto
    "two_wheeler": 25,   # bike/scooter in traffic
    "transit":     18,   # bus + walk overhead
    "company_cab": 30,   # slightly faster (dedicated route, less stopping)
}
_DEFAULT_SPEED_KMH = 25

# Google Maps mode mapping
_GMAPS_MODE = {
    "driving":     "driving",
    "two_wheeler": "driving",   # Google doesn't have two_wheeler in all regions
    "transit":     "transit",
    "company_cab": "driving",
}

GOOGLE_MAPS_API_URL = (
    "https://maps.googleapis.com/maps/api/distancematrix/json"
)


def _api_key() -> str:
    return os.environ.get("GOOGLE_MAPS_API_KEY", "")


def _cache_key(orig_lat, orig_lng, dest_lat, dest_lng, mode: str) -> str:
    s = f"{orig_lat:.4f},{orig_lng:.4f}→{dest_lat:.4f},{dest_lng:.4f}|{mode}"
    return hashlib.sha256(s.encode()).hexdigest()[:20]


def _init_cache(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS travel_time_cache (
            cache_key  TEXT PRIMARY KEY,
            minutes    REAL,
            source     TEXT,
            created_at INTEGER DEFAULT (strftime('%s','now'))
        )
    """)
    conn.commit()


def _get_cached(conn: sqlite3.Connection, key: str) -> float | None:
    row = conn.execute(
        "SELECT minutes FROM travel_time_cache WHERE cache_key = ?", (key,)
    ).fetchone()
    return row[0] if row else None


def _set_cached(conn: sqlite3.Connection, key: str, minutes: float, source: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO travel_time_cache (cache_key, minutes, source) VALUES (?, ?, ?)",
        (key, minutes, source),
    )
    conn.commit()


def _heuristic_minutes(distance_km: float, mode: str) -> float:
    """Estimate travel time from straight-line distance using mode-specific speed."""
    speed = _HEURISTIC_SPEED_KMH.get(mode, _DEFAULT_SPEED_KMH)
    # Add 20% overhead for route inefficiency (roads aren't straight lines)
    road_km = distance_km * 1.25
    return round(road_km / speed * 60, 1)


def _gmaps_minutes(
    orig_lat: float, orig_lng: float,
    dest_lat: float, dest_lng: float,
    mode: str,
) -> float | None:
    """Query Google Maps Distance Matrix API. Returns minutes or None on failure."""
    api_key = _api_key()
    if not api_key:
        return None
    gmode = _GMAPS_MODE.get(mode, "driving")
    params = {
        "origins":      f"{orig_lat},{orig_lng}",
        "destinations": f"{dest_lat},{dest_lng}",
        "mode":         gmode,
        "key":          api_key,
        "units":        "metric",
    }
    if gmode == "transit":
        # Use weekday morning rush hour for realistic transit time
        # Use next Monday 9am (epoch)
        import datetime
        now = datetime.datetime.now()
        days_ahead = (7 - now.weekday()) % 7 or 7
        next_monday = now + datetime.timedelta(days=days_ahead)
        monday_9am = next_monday.replace(hour=9, minute=0, second=0, microsecond=0)
        params["departure_time"] = int(monday_9am.timestamp())

    try:
        r = requests.get(GOOGLE_MAPS_API_URL, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        if not data.get("rows") or not data["rows"][0].get("elements"):
            logger.warning("Google Maps: empty response for mode=%s", mode)
            return None
        element = data["rows"][0]["elements"][0]
        if element["status"] != "OK":
            logger.warning("Google Maps: status=%s for %s mode", element["status"], mode)
            return None
        duration = element.get("duration_in_traffic") or element.get("duration")
        return round(duration["value"] / 60, 1)  # seconds → minutes
    except Exception:
        logger.exception("Google Maps API call failed")
        return None


def get_travel_time(
    orig_lat: float,
    orig_lng: float,
    dest_lat: float,
    dest_lng: float,
    mode: str,
    conn: sqlite3.Connection,
) -> tuple[float, str]:
    """
    Return (travel_time_minutes, source) where source is "gmaps" or "heuristic".
    Results are cached in SQLite.
    """
    _init_cache(conn)
    key = _cache_key(orig_lat, orig_lng, dest_lat, dest_lng, mode)

    cached = _get_cached(conn, key)
    if cached is not None:
        return cached, "cached"

    # Try Google Maps first
    minutes = _gmaps_minutes(orig_lat, orig_lng, dest_lat, dest_lng, mode)
    source = "gmaps"

    if minutes is None:
        # Fallback to heuristic
        dist_km = haversine((orig_lat, orig_lng), (dest_lat, dest_lng), unit=Unit.KILOMETERS)
        minutes = _heuristic_minutes(dist_km, mode)
        source = "heuristic"

    _set_cached(conn, key, minutes, source)
    return minutes, source
