import hashlib
import logging
import re
import time
import sqlite3
from geopy.geocoders import Nominatim
from haversine import haversine, Unit
from src.db import cache_geocode, get_cached_geocode
from src.models import Listing
from config import (
    MAX_RADIUS_KM,
    ZONE_SUPER_CLOSE_KM, ZONE_PREFERRED_KM, ZONE_NEARBY_KM,
    FAR_MAX_PRICE, FAR_MIN_RATING,
    PRIORITY_LOCALITIES, CITY,
)

logger = logging.getLogger(__name__)

ZONE_SUPER_CLOSE = "SUPER CLOSE"
ZONE_PREFERRED   = "PREFERRED"
ZONE_NEARBY      = "NEARBY"
ZONE_ACCEPTABLE  = "ACCEPTABLE"
ZONE_FAR         = "FAR BUT CHEAP"

_geocoder = None


def _get_geocoder() -> Nominatim:
    global _geocoder
    if _geocoder is None:
        _geocoder = Nominatim(user_agent="rental-monitor/1.0", timeout=10)
    return _geocoder


def _hash_address(address: str) -> str:
    return hashlib.sha256(address.lower().strip().encode()).hexdigest()


def is_priority_locality(address: str) -> bool:
    addr_lower = address.lower()
    return any(loc in addr_lower for loc in PRIORITY_LOCALITIES)


def _locality_fallback(address: str) -> str | None:
    skip = re.compile(
        r"^(chennai|india|tamil\s*nadu)$|"
        r"^\d+[/\\]?\d*[a-z]?$|"
        r"\b(street|st\.|road|rd\.|nagar|colony|layout|cross|"
        r"main|avenue|lane|gst|looks|apartment|independent|house|market)\b",
        re.IGNORECASE,
    )
    parts = [p.strip() for p in re.split(r"[,;]+", address)]
    meaningful = [p for p in parts if len(p) > 3 and not skip.search(p)]
    if len(meaningful) >= 2:
        return meaningful[-2]
    if meaningful:
        return meaningful[-1]
    return None


def geocode_listing(address: str, conn: sqlite3.Connection) -> tuple[float, float] | None:
    address_hash = _hash_address(address)
    cached = get_cached_geocode(conn, address_hash)
    if cached:
        return cached

    geocoder = _get_geocoder()
    candidates = [f"{address}, {CITY}, India"]
    locality = _locality_fallback(address)
    if locality and locality.lower() != address.lower().strip():
        candidates.append(f"{locality}, {CITY}, India")

    # Rough bounding box for the configured city (works for most Indian cities)
    _LAT_MIN, _LAT_MAX = 12.7, 13.3
    _LNG_MIN, _LNG_MAX = 79.8, 80.4

    for query in candidates:
        try:
            time.sleep(1)
            location = geocoder.geocode(query)
            if location is not None:
                lat, lng = location.latitude, location.longitude
                if not (_LAT_MIN <= lat <= _LAT_MAX and _LNG_MIN <= lng <= _LNG_MAX):
                    continue
                cache_geocode(conn, address_hash, lat, lng)
                return (lat, lng)
        except Exception:
            logger.exception("Geocoding failed for query: %s", query)

    logger.warning("Could not geocode address: %s", address)
    return None


def assign_zone(
    distance_km: float,
    price: int,
    rating: float | None,
    max_radius_km: float = MAX_RADIUS_KM,
) -> str | None:
    if distance_km <= ZONE_SUPER_CLOSE_KM:
        return ZONE_SUPER_CLOSE
    if distance_km <= ZONE_PREFERRED_KM:
        return ZONE_PREFERRED
    if distance_km <= ZONE_NEARBY_KM and max_radius_km >= ZONE_NEARBY_KM:
        return ZONE_NEARBY
    if distance_km <= max_radius_km:
        return ZONE_ACCEPTABLE
    if (max_radius_km > ZONE_NEARBY_KM
            and price <= FAR_MAX_PRICE
            and rating is not None
            and rating >= FAR_MIN_RATING):
        return ZONE_FAR
    return None


def apply_distance_filter(
    listings: list[Listing],
    conn: sqlite3.Connection,
    office_lat: float,
    office_lng: float,
    max_radius_km: float = MAX_RADIUS_KM,
) -> list[tuple[Listing, str, float | None]]:
    results = []
    for listing in listings:
        coords = geocode_listing(listing.address, conn)
        if coords is None:
            listing.lat = None
            listing.lng = None
            results.append((listing, "Distance unknown", None))
            continue

        lat, lng = coords
        listing.lat = lat
        listing.lng = lng
        distance_km = haversine((office_lat, office_lng), (lat, lng), unit=Unit.KILOMETERS)
        zone = assign_zone(distance_km, listing.price, listing.rating, max_radius_km)
        if zone is not None:
            results.append((listing, zone, distance_km))

    return results
