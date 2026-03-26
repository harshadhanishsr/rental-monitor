"""
One-shot fetch: scrape all sources, filter, print + send top matches.
Usage:  python fetch_now.py
"""
import io
import logging
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("fetch_now")

from config import OFFICE_LAT, OFFICE_LNG, MAX_RADIUS_KM, PROPERTY_LABEL, MAX_RENT
from src.db import init_db, get_connection
from src.scheduler import run_all_scrapers, apply_property_filter
from src.filters.distance_filter import apply_distance_filter, is_priority_locality
from src.notifier import telegram_bot as _tg
from src.notifier.whatsapp import send_alert, _get_client, format_message

DB_PATH = os.environ.get("DB_PATH", "data/rental_monitor.db")


def main():
    conn = get_connection(DB_PATH)
    init_db(conn)

    logger.info("Scraping all sources for %s ≤ ₹%d in %s…", PROPERTY_LABEL, MAX_RENT, "Chennai")
    raw = run_all_scrapers()
    logger.info("Raw listings: %d", len(raw))

    filtered = apply_property_filter(raw)
    logger.info("After property filter: %d", len(filtered))

    candidates = apply_distance_filter(filtered, conn, OFFICE_LAT, OFFICE_LNG, max_radius_km=MAX_RADIUS_KM)
    logger.info("Within %.1f km: %d listings", MAX_RADIUS_KM, len(candidates))

    confirmed = [(l, z, d) for l, z, d in candidates if d is not None]
    logger.info("Geocoded: %d confirmed", len(confirmed))
    candidates = confirmed

    if not candidates:
        print("\nNo listings found within the configured radius.")
        return

    candidates.sort(key=lambda x: (
        0 if is_priority_locality(x[0].address) else 1,
        x[2],
        x[0].price,
    ))

    print(f"\n{'='*60}")
    print(f"  RESULTS — {len(candidates)} listings within {MAX_RADIUS_KM:.0f}km")
    print(f"{'='*60}\n")

    for i, (listing, zone, dist_km) in enumerate(candidates, 1):
        priority = " [PRIORITY AREA]" if is_priority_locality(listing.address) else ""
        dist_str = f"{dist_km:.1f}km" if dist_km is not None else "dist unknown"
        print(f"{i:>2}. [{zone}] {dist_str}{priority}")
        print(f"     {listing.title}")
        print(f"     📍 {listing.address}")
        print(f"     💰 ₹{listing.price:,}/month | {listing.furnishing}")
        print(f"     🌐 {listing.source} — {listing.url}")
        if listing.lat and listing.lng:
            print(f"     🗺  https://maps.google.com/?q={listing.lat},{listing.lng}")
        print()

    top = candidates[:10]
    print(f"Sending {len(top)} matches via Telegram…")

    use_telegram = bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))
    within_5 = sum(1 for _, _, d in top if d is not None and d <= 5.0)
    header = (
        f"🏠 *Rental Search Results*\n"
        f"{len(candidates)} listings within {MAX_RADIUS_KM:.0f}km\n"
        f"⭐ {within_5} within 5km\nSending all matches:"
    )

    if use_telegram:
        _tg.send_text(header)
        for listing, zone, dist_km in top:
            try:
                _tg.send_alert(listing, zone, dist_km)
            except Exception:
                logger.exception("Failed to send alert for %s/%s", listing.source, listing.id)
    else:
        client = _get_client()
        client.messages.create(
            body=header,
            from_=os.environ["TWILIO_WHATSAPP_FROM"],
            to=os.environ["WHATSAPP_TO"],
        )
        for listing, zone, dist_km in top:
            try:
                send_alert(listing, zone, dist_km)
            except Exception:
                logger.exception("Failed to send alert for %s/%s", listing.source, listing.id)

    print("Done. Check your Telegram!")


if __name__ == "__main__":
    main()
