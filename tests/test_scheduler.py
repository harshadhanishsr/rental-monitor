import sqlite3
import pytest
from unittest.mock import MagicMock, patch
from src.db import init_db, add_pending_alert
from src.models import Listing
from src.scheduler import run_cycle


@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    yield conn
    conn.close()


def make_listing(**kwargs):
    defaults = dict(id="1", source="nobroker", title="1 BHK in Chromepet",
                    address="Chromepet", price=12000, url="https://nobroker.in/1")
    return Listing(**{**defaults, **kwargs})


def test_run_cycle_sends_new_listing(db_conn):
    listing = make_listing()
    with (
        patch("src.scheduler.run_all_scrapers", return_value=[listing]),
        patch("src.scheduler.apply_property_filter", return_value=[listing]),
        patch("src.scheduler.apply_distance_filter", return_value=[(listing, "PREFERRED", 3.2)]),
        patch("src.scheduler.send_alert", return_value="SMtest"),
        patch("src.scheduler.mark_seen") as mock_mark,
    ):
        run_cycle(db_conn, office_lat=12.97, office_lng=80.14)
        mock_mark.assert_called_once_with(db_conn, "1", "nobroker")


def test_run_cycle_skips_seen_listing(db_conn):
    from src.db import mark_seen
    mark_seen(db_conn, "1", "nobroker")
    listing = make_listing()
    with (
        patch("src.scheduler.run_all_scrapers", return_value=[listing]),
        patch("src.scheduler.apply_property_filter", return_value=[listing]),
        patch("src.scheduler.apply_distance_filter", return_value=[(listing, "PREFERRED", 3.2)]),
        patch("src.scheduler.send_alert") as mock_send,
    ):
        run_cycle(db_conn, office_lat=12.97, office_lng=80.14)
        mock_send.assert_not_called()


def test_run_cycle_queues_on_twilio_failure(db_conn):
    listing = make_listing()
    with (
        patch("src.scheduler.run_all_scrapers", return_value=[listing]),
        patch("src.scheduler.apply_property_filter", return_value=[listing]),
        patch("src.scheduler.apply_distance_filter", return_value=[(listing, "PREFERRED", 3.2)]),
        patch("src.scheduler.send_alert", side_effect=Exception("Twilio down")),
        patch("src.scheduler.add_pending_alert") as mock_queue,
    ):
        run_cycle(db_conn, office_lat=12.97, office_lng=80.14)
        mock_queue.assert_called_once()


def test_run_cycle_retries_pending_alerts(db_conn):
    listing = make_listing(id="pending1")
    add_pending_alert(db_conn, listing, "PREFERRED", 3.0)

    with (
        patch("src.scheduler.run_all_scrapers", return_value=[]),
        patch("src.scheduler.apply_property_filter", return_value=[]),
        patch("src.scheduler.apply_distance_filter", return_value=[]),
        patch("src.scheduler.send_alert", return_value="SMretried"),
        patch("src.scheduler.resolve_pending_alert") as mock_resolve,
    ):
        run_cycle(db_conn, office_lat=12.97, office_lng=80.14)
        mock_resolve.assert_called_once()
