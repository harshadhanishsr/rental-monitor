import hashlib
import logging
import re
import time
import sqlite3
from geopy.geocoders import Nominatim
from haversine import haversine, Unit
from src.db import cache_geocode, get_cached_geocode
from src.models import Listing

logger = logging.getLogger(__name__)

# Distance zones relative to office
ZONE_SUPER_CLOSE = "SUPER CLOSE"    # ≤2 km  — walkable / short auto ride
ZONE_PREFERRED   = "PREFERRED"      # 2–5 km — comfortable daily commute
ZONE_NEARBY      = "NEARBY"         # 5–8 km — easy bus/metro
ZONE_ACCEPTABLE  = "ACCEPTABLE"     # 8–10 km — still within target radius
ZONE_FAR         = "FAR BUT CHEAP"  # >10 km — only if price ≤10K AND rating ≥4

FAR_MAX_PRICE   = 10_000
FAR_MIN_RATING  = 4.0

# Localities known to be close/convenient to the Chromepet office.
# Listings whose address contains any of these get a star in the alert.
PRIORITY_LOCALITIES = {
    "chromepet", "pallavaram", "nanganallur", "pammal", "selaiyur",
    "st. thomas mount", "meenambakkam", "tirusulam", "alandur",
    "kilkattalai", "perungalathur", "mudichur", "tambaram",
    "ullagaram", "puzhuthivakkam", "medavakkam",
}

_geocoder = None


def _get_geocoder() -> Nominatim:
    global _geocoder
    if _geocoder is None:
        _geocoder = Nominatim(user_agent="rental-monitor/1.0", timeout=10)
    return _geocoder


def _hash_address(address: str) -> str:
    return hashlib.sha256(address.lower().strip().encode()).hexdigest()


def is_priority_locality(address: str) -> bool:
    """Return True if the address contains any known priority locality name."""
    addr_lower = address.lower()
    return any(loc in addr_lower for loc in PRIORITY_LOCALITIES)


def _locality_fallback(address: str) -> str | None:
    """
    Extract just the locality name from a messy address string.

    Strategy: split on commas, drop generic tokens ("Chennai", short tokens,
    tokens that look like street addresses), return the last meaningful token.

    "SSM Nagar, Perungalathur, Chennai"         → "Perungalathur"
    "Teachers Colony, Kolathur, Chennai"         → "Kolathur"
    "Industrial Area, Saidapet, GST Road, Chennai" → "Saidapet"
    "Looks like apartment, Chennai"              → None
    """
    skip = re.compile(
        r"^(chennai|india|tamil\s*nadu)$|"
        r"^\d+[/\\]?\d*[a-z]?$|"        # house numbers
        r"\b(street|st\.|road|rd\.|nagar|colony|layout|cross|"
        r"main|avenue|lane|gst|looks|apartment|independent|house|market)\b",
        re.IGNORECASE,
    )
    parts = [p.strip() for p in re.split(r"[,;]+", address)]
    meaningful = [p for p in parts if len(p) > 3 and not skip.search(p)]
    # Return second-to-last (locality) or last if only one left
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
    candidates = [f"{address}, Chennai, India"]
    locality = _locality_fallback(address)
    if locality and locality.lower() != address.lower().strip():
        candidates.append(f"{locality}, Chennai, India")

    # Chennai bounding box — discard any result outside this range
    _LAT_MIN, _LAT_MAX = 12.7, 13.3
    _LNG_MIN, _LNG_MAX = 79.8, 80.4

    for query in candidates:
        try:
            time.sleep(1)  # Nominatim rate limit: 1 req/sec
            location = geocoder.geocode(query)
            if location is not None:
                lat, lng = location.latitude, location.longitude
                if not (_LAT_MIN <= lat <= _LAT_MAX and _LNG_MIN <= lng <= _LNG_MAX):
                    logger.debug(
                        "Geocoded '%s' outside Chennai bounds (%.4f, %.4f) — skipping",
                        query, lat, lng,
                    )
                    continue
                cache_geocode(conn, address_hash, lat, lng)
                logger.debug("Geocoded '%s' → (%.4f, %.4f)", address, lat, lng)
                return (lat, lng)
        except Exception:
            logger.exception("Geocoding failed for query: %s", query)

    logger.warning("Could not geocode address: %s", address)
    return None


def assign_zone(
    distance_km: float,
    price: int,
    rating: float | None,
    max_radius_km: float = 10.0,
) -> str | None:
    if distance_km <= 2.0:
        return ZONE_SUPER_CLOSE
    if distance_km <= 5.0:
        return ZONE_PREFERRED
    if distance_km <= 8.0 and max_radius_km >= 8.0:
        return ZONE_NEARBY
    if distance_km <= 10.0 and max_radius_km >= 10.0:
        return ZONE_ACCEPTABLE
    # FAR zone: only if price ≤10K AND rating ≥4.0 and caller allows it
    if max_radius_km > 10.0 and price <= FAR_MAX_PRICE and rating is not None and rating >= FAR_MIN_RATING:
        return ZONE_FAR
    return None


def apply_distance_filter(
    listings: list[Listing],
    conn: sqlite3.Connection,
    office_lat: float,
    office_lng: float,
    max_radius_km: float = 10.0,
) -> list[tuple[Listing, str, float | None]]:
    """
    Returns list of (listing, zone, distance_km) for listings that pass the filter.
    distance_km is None if geocoding failed (listing still included as unknown distance).
    """
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
