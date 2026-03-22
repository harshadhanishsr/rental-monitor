import hashlib
import logging
import time
import sqlite3
from geopy.geocoders import Nominatim
from haversine import haversine, Unit
from src.db import cache_geocode, get_cached_geocode
from src.models import Listing

logger = logging.getLogger(__name__)

ZONE_PREFERRED = "PREFERRED"
ZONE_ACCEPTABLE = "ACCEPTABLE"
ZONE_FAR = "FAR BUT WORTH IT"

FAR_MAX_PRICE = 10_000
FAR_MIN_RATING = 4.0

_geocoder = None


def _get_geocoder() -> Nominatim:
    global _geocoder
    if _geocoder is None:
        _geocoder = Nominatim(user_agent="rental-monitor/1.0")
    return _geocoder


def _hash_address(address: str) -> str:
    return hashlib.sha256(address.lower().strip().encode()).hexdigest()


def geocode_listing(address: str, conn: sqlite3.Connection) -> tuple[float, float] | None:
    address_hash = _hash_address(address)
    cached = get_cached_geocode(conn, address_hash)
    if cached:
        return cached

    try:
        time.sleep(1)  # Nominatim rate limit: 1 req/sec
        location = _get_geocoder().geocode(f"{address}, Chennai, India")
        if location is None:
            return None
        lat, lng = location.latitude, location.longitude
        cache_geocode(conn, address_hash, lat, lng)
        return (lat, lng)
    except Exception:
        logger.exception("Geocoding failed for address: %s", address)
        return None


def assign_zone(distance_km: float, price: int, rating: float | None) -> str | None:
    if distance_km <= 5.0:
        return ZONE_PREFERRED
    if distance_km <= 10.0:
        return ZONE_ACCEPTABLE
    # FAR zone: price <= 10K AND rating >= 4.0
    if price <= FAR_MAX_PRICE and rating is not None and rating >= FAR_MIN_RATING:
        return ZONE_FAR
    return None


def apply_distance_filter(
    listings: list[Listing],
    conn: sqlite3.Connection,
    office_lat: float,
    office_lng: float,
) -> list[tuple[Listing, str, float | None]]:
    """
    Returns list of (listing, zone, distance_km) for listings that should be alerted.
    distance_km is None if geocoding failed.
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
        zone = assign_zone(distance_km, listing.price, listing.rating)
        if zone is not None:
            results.append((listing, zone, distance_km))

    return results
