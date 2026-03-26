import logging
import sqlite3
from src.db import (
    is_seen, mark_seen, add_pending_alert,
    get_pending_alerts, resolve_pending_alert,
    increment_retry, delete_stale_pending,
)
from src.filters.property_filter import passes_property_filter
from src.filters.distance_filter import apply_distance_filter
from src.models import Listing
from src.notifier.whatsapp import send_alert as _whatsapp_alert
from src.notifier import telegram_bot as _tg
import os


def send_alert(listing, zone, distance_km):
    """Send via Telegram if configured, otherwise fall back to Twilio WhatsApp."""
    if os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"):
        ok = _tg.send_alert(listing, zone, distance_km)
        if ok:
            return "telegram"
    return _whatsapp_alert(listing, zone, distance_km)

logger = logging.getLogger(__name__)

SCRAPERS = [
    "src.scrapers.nobroker",
    "src.scrapers.magicbricks",
    "src.scrapers.acres99",
    "src.scrapers.olx",
    "src.scrapers.housing",
    "src.scrapers.quikr",
]


def run_all_scrapers() -> list[Listing]:
    import importlib
    all_listings = []
    for module_path in SCRAPERS:
        try:
            module = importlib.import_module(module_path)
            results = module.scrape()
            logger.info("Scraped %d listings from %s", len(results), module_path)
            all_listings.extend(results)
        except Exception:
            logger.exception("Scraper failed: %s", module_path)
    return all_listings


def apply_property_filter(listings: list[Listing]) -> list[Listing]:
    return [l for l in listings if passes_property_filter(l)]


def run_cycle(conn: sqlite3.Connection, office_lat: float, office_lng: float) -> None:
    logger.info("Starting run cycle")

    # Step 1: Retry pending alerts
    delete_stale_pending(conn, max_retries=48)
    for row_id, listing, zone, distance_km in get_pending_alerts(conn):
        try:
            sid = send_alert(listing, zone, distance_km)
            resolve_pending_alert(conn, row_id)
            mark_seen(conn, listing.id, listing.source)
            logger.info("Retried pending alert %d → SID %s", row_id, sid)
        except Exception:
            increment_retry(conn, row_id)
            logger.warning("Pending alert %d retry failed", row_id)

    # Step 2: Scrape
    raw = run_all_scrapers()
    filtered = apply_property_filter(raw)
    logger.info("%d listings after property filter", len(filtered))

    # Step 3: Distance filter
    candidates = apply_distance_filter(filtered, conn, office_lat, office_lng)
    logger.info("%d listings after distance filter", len(candidates))

    # Step 4: Dedup + alert
    for listing, zone, distance_km in candidates:
        if is_seen(conn, listing.id, listing.source):
            continue
        try:
            sid = send_alert(listing, zone, distance_km)
            mark_seen(conn, listing.id, listing.source)
            logger.info("Alerted listing %s/%s (SID: %s)", listing.source, listing.id, sid)
        except Exception:
            logger.exception("Failed to send alert for %s/%s — queuing", listing.source, listing.id)
            add_pending_alert(conn, listing, zone, distance_km)

    logger.info("Run cycle complete")
