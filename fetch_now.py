"""
One-shot fetch: scrape all sources, filter to 5km radius, print + WhatsApp top matches.
Usage: python fetch_now.py
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

OFFICE_LAT   = float(os.environ.get("OFFICE_LAT", "12.9698"))
OFFICE_LNG   = float(os.environ.get("OFFICE_LNG", "80.1409"))
MAX_RADIUS   = 5.0   # km — tight 5km run
DB_PATH      = os.environ.get("DB_PATH", "data/rental_monitor.db")

from src.db import init_db, get_connection
from src.scheduler import run_all_scrapers, apply_property_filter
from src.filters.distance_filter import apply_distance_filter, is_priority_locality
from src.notifier.whatsapp import send_alert, _get_client, format_message


def main():
    conn = get_connection(DB_PATH)
    init_db(conn)

    logger.info("Scraping all sources (Chennai-wide)…")
    raw = run_all_scrapers()
    logger.info("Raw listings: %d", len(raw))

    filtered = apply_property_filter(raw)
    logger.info("After property filter: %d", len(filtered))

    candidates = apply_distance_filter(filtered, conn, OFFICE_LAT, OFFICE_LNG, max_radius_km=MAX_RADIUS)
    logger.info("Within %.1f km: %d listings", MAX_RADIUS, len(candidates))

    # For strict radius mode drop listings where geocoding failed (unknown distance)
    confirmed = [(l, z, d) for l, z, d in candidates if d is not None]
    unknown   = [(l, z, d) for l, z, d in candidates if d is None]
    logger.info("Geocoded: %d confirmed, %d unknown distance (skipped)", len(confirmed), len(unknown))
    candidates = confirmed

    if not candidates:
        print("\nNo listings with confirmed location found within 5km.")
        if unknown:
            print(f"({len(unknown)} listings were found but geocoding failed — check addresses)")
        return

    # Sort: priority locality first, then by distance, then by price
    candidates.sort(key=lambda x: (
        0 if is_priority_locality(x[0].address) else 1,
        x[2],
        x[0].price,
    ))

    print(f"\n{'='*60}")
    print(f"  RESULTS — {len(candidates)} listings within 5km of office")
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

    # Send top 5 via WhatsApp
    top = candidates[:5]
    print(f"Sending top {len(top)} matches to WhatsApp…")

    client = _get_client()
    from_number = os.environ["TWILIO_WHATSAPP_FROM"]
    to_number   = os.environ["WHATSAPP_TO"]

    # Summary header message
    header_msg = (
        f"🏠 *5km Search Results* — {len(candidates)} listings found\n"
        f"Sending top {len(top)} matches now:"
    )
    client.messages.create(body=header_msg, from_=from_number, to=to_number)

    for listing, zone, dist_km in top:
        try:
            send_alert(listing, zone, dist_km)
            logger.info("Sent alert for %s/%s", listing.source, listing.id)
        except Exception:
            logger.exception("Failed to send alert for %s/%s", listing.source, listing.id)

    print("Done. Check your WhatsApp!")


if __name__ == "__main__":
    main()
