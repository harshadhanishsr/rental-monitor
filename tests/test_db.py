# tests/test_db.py
import json
from datetime import datetime, timezone
from src.db import init_db, is_seen, mark_seen, add_pending_alert, get_pending_alerts, resolve_pending_alert, increment_retry, delete_stale_pending, cache_geocode, get_cached_geocode
from src.models import Listing


def make_listing(**kwargs):
    defaults = dict(id="1", source="nobroker", title="T", address="A", price=12000, url="http://x.com")
    return Listing(**{**defaults, **kwargs})


def test_is_seen_false_initially(db_conn):
    assert is_seen(db_conn, "1", "nobroker") is False


def test_mark_seen_and_is_seen(db_conn):
    mark_seen(db_conn, "1", "nobroker")
    assert is_seen(db_conn, "1", "nobroker") is True


def test_different_source_not_seen(db_conn):
    mark_seen(db_conn, "1", "nobroker")
    assert is_seen(db_conn, "1", "olx") is False


def test_add_and_get_pending_alert(db_conn):
    listing = make_listing(id="99", source="olx")
    add_pending_alert(db_conn, listing, "PREFERRED", 3.2)
    rows = get_pending_alerts(db_conn)
    assert len(rows) == 1
    row_id, restored, zone, distance_km = rows[0]
    assert restored.id == "99"
    assert restored.source == "olx"
    assert zone == "PREFERRED"
    assert distance_km == 3.2


def test_resolve_pending_alert(db_conn):
    listing = make_listing(id="42", source="quikr")
    add_pending_alert(db_conn, listing, "ACCEPTABLE", 7.0)
    row_id, _, _, _ = get_pending_alerts(db_conn)[0]
    resolve_pending_alert(db_conn, row_id)
    assert get_pending_alerts(db_conn) == []


def test_increment_retry(db_conn):
    listing = make_listing()
    add_pending_alert(db_conn, listing, "PREFERRED", 2.0)
    row_id, _, _, _ = get_pending_alerts(db_conn)[0]
    increment_retry(db_conn, row_id)
    rows = get_pending_alerts(db_conn)
    assert rows[0][0] == row_id  # still there


def test_delete_stale_pending(db_conn):
    listing = make_listing()
    add_pending_alert(db_conn, listing, "PREFERRED", 1.5)
    row_id, _, _, _ = get_pending_alerts(db_conn)[0]
    db_conn.execute("UPDATE pending_alerts SET retry_count = 48 WHERE id = ?", (row_id,))
    db_conn.commit()
    delete_stale_pending(db_conn, max_retries=48)
    assert get_pending_alerts(db_conn) == []


def test_geocode_cache_miss(db_conn):
    assert get_cached_geocode(db_conn, "abc123") is None


def test_geocode_cache_hit(db_conn):
    cache_geocode(db_conn, "abc123", 12.97, 80.14)
    result = get_cached_geocode(db_conn, "abc123")
    assert result == (12.97, 80.14)
