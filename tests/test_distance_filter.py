import sqlite3
import pytest
from unittest.mock import patch, MagicMock
from src.db import init_db
from src.models import Listing
from src.filters.distance_filter import assign_zone, geocode_listing, ZONE_PREFERRED, ZONE_ACCEPTABLE, ZONE_FAR


@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    yield conn
    conn.close()


def make_listing(**kwargs):
    defaults = dict(id="1", source="nobroker", title="1 BHK",
                    address="Chromepet Main Road", price=12000, url="http://x.com")
    return Listing(**{**defaults, **kwargs})


def test_zone_preferred():
    assert assign_zone(3.0, 12000, 4.5) == ZONE_PREFERRED

def test_zone_acceptable():
    assert assign_zone(7.5, 12000, None) == ZONE_ACCEPTABLE

def test_zone_far_qualifies():
    assert assign_zone(12.0, 9000, 4.2) == ZONE_FAR

def test_zone_far_price_too_high():
    assert assign_zone(12.0, 11000, 4.5) is None

def test_zone_far_no_rating():
    assert assign_zone(12.0, 9000, None) is None

def test_zone_far_rating_too_low():
    assert assign_zone(12.0, 9000, 3.5) is None

def test_geocode_uses_cache(db_conn):
    from src.db import cache_geocode
    import hashlib
    address = "Chromepet, Chennai"
    address_hash = hashlib.sha256(address.lower().strip().encode()).hexdigest()
    cache_geocode(db_conn, address_hash, 12.97, 80.14)

    with patch("src.filters.distance_filter.Nominatim") as mock_nom:
        result = geocode_listing(address, db_conn)
    mock_nom.assert_not_called()
    assert result == (12.97, 80.14)

def test_geocode_calls_nominatim_on_miss(db_conn):
    mock_location = MagicMock()
    mock_location.latitude = 12.95
    mock_location.longitude = 80.15

    with patch("src.filters.distance_filter.Nominatim") as MockNom:
        with patch("src.filters.distance_filter.time.sleep"):
            with patch("src.filters.distance_filter._geocoder", None):
                MockNom.return_value.geocode.return_value = mock_location
                result = geocode_listing("Some Address, Chennai", db_conn)

    assert result == (12.95, 80.15)

def test_geocode_returns_none_on_failure(db_conn):
    with patch("src.filters.distance_filter.Nominatim") as MockNom:
        with patch("src.filters.distance_filter.time.sleep"):
            with patch("src.filters.distance_filter._geocoder", None):
                MockNom.return_value.geocode.return_value = None
                result = geocode_listing("Unknown Place XYZ", db_conn)
    assert result is None
