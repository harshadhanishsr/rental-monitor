"""
Rental monitor — scrapes every hour, sends new listings to Telegram.

Each alert has tap-to-track buttons:
  [⭐ Shortlist]  [📞 Contacted]  [👎 Pass]

Bot commands:
  /summary   — all tracked listings
  /shortlist — shortlisted only

Logs to data/monitor.log
"""
import io
import logging
import os
import sys
import time
import hashlib
import sqlite3
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

os.makedirs("data", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("data/monitor.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("monitor")

from config import (
    OFFICE_LAT, OFFICE_LNG, MAX_RADIUS_KM,
    PROPERTY_LABEL, CITY, CHECK_INTERVAL_SECONDS,
)
from src.db import (
    init_db, get_connection, is_seen, mark_seen,
    tracker_add, tracker_set_msg_id,
)
from src.scheduler import run_all_scrapers, apply_property_filter
from src.filters.distance_filter import apply_distance_filter, is_priority_locality
from src.travel_time import get_travel_time
from src.notifier.tracker_bot import send_with_buttons, start_polling
import requests as _req

DB_PATH = os.environ.get("DB_PATH", "data/rental_monitor.db")


def _tg_send(text: str):
    token   = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    try:
        _req.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text,
                  "parse_mode": "Markdown", "disable_web_page_preview": False},
            timeout=10,
        ).raise_for_status()
    except Exception:
        logger.exception("Telegram send failed")


def _format_alert(listing, dist_km, travel_minutes, walk_minutes, time_source) -> str:
    priority = " ⭐ PRIORITY" if is_priority_locality(listing.address) else ""
    broker   = "No broker" if "nobroker" in listing.source.lower() else "Check for broker"
    bachelor = "Bachelors OK" if listing.bachelors_allowed else "Occupancy unspecified"
    dist_str = f"{dist_km:.1f}km" if dist_km is not None else "dist unknown"

    if travel_minutes is not None:
        est    = "~" if time_source == "heuristic" else ""
        bar    = "🟢" if travel_minutes <= 20 else "🟡" if travel_minutes <= 40 else "🔴"
        commute = f"{bar} {est}{travel_minutes:.0f} min by transit"
        if walk_minutes is not None:
            commute += f" (~{walk_minutes:.0f} min walking)"
    else:
        commute = f"{dist_str} from office"

    lines = [
        f"🏠 *New {PROPERTY_LABEL}* | {dist_str} from office{priority}",
        "─────────────────────────────",
        f"📍 {listing.address}",
        f"💰 ₹{listing.price:,}/month | {listing.furnishing.title()}",
        f"{bachelor} | {broker}",
        f"🚌 {commute}",
    ]
    if listing.rating is not None:
        review = f' — "{listing.review_snippet}"' if listing.review_snippet else ""
        lines.append(f"⭐ {listing.rating}/5{review}")
    if listing.lat and listing.lng:
        lines.append(f"🗺 [View on Maps](https://maps.google.com/?q={listing.lat},{listing.lng})")
    lines += [
        f"🌐 {listing.source.title()}",
        f"🔗 [Open listing]({listing.url})",
        f"_Found: {datetime.now(timezone.utc).strftime('%H:%M, %d %b %Y')} UTC_",
    ]
    return "\n".join(lines)


def run_cycle(conn: sqlite3.Connection):
    logger.info("=" * 55)
    logger.info("Cycle start — %s", datetime.now().strftime("%H:%M %d %b %Y"))
    logger.info("=" * 55)

    raw      = run_all_scrapers()
    filtered = apply_property_filter(raw)
    logger.info("Scraped %d raw -> %d after property filter", len(raw), len(filtered))

    candidates = apply_distance_filter(
        filtered, conn, OFFICE_LAT, OFFICE_LNG, max_radius_km=MAX_RADIUS_KM
    )
    logger.info("%d within %.0fkm of office", len(candidates), MAX_RADIUS_KM)

    candidates = [(l, z, d) for l, z, d in candidates if d is not None]
    candidates.sort(key=lambda x: (
        0 if is_priority_locality(x[0].address) else 1,
        x[2],
        x[0].price,
    ))

    new_count = 0
    for listing, zone, dist_km in candidates:
        seen_key = f"{listing.source}_{listing.id}"
        if is_seen(conn, seen_key, "solo"):
            continue

        mins, src, walk = get_travel_time(
            listing.lat, listing.lng,
            OFFICE_LAT, OFFICE_LNG,
            "transit", conn,
        )

        # Skip listings >10km unless transit is under 60 min
        if dist_km > 10.0 and (mins is None or mins > 60):
            logger.info("Skipped (far+slow): %s | %.1fkm | %s min",
                        listing.address[:45], dist_km, f"{mins:.0f}" if mins else "?")
            mark_seen(conn, seen_key, "solo")
            continue

        msg         = _format_alert(listing, dist_km, mins, walk, src)
        tracking_id = hashlib.sha256(f"{listing.source}:{listing.id}".encode()).hexdigest()[:16]

        # Store in tracker DB before sending
        tracker_add(conn, tracking_id, listing.address, listing.price,
                    listing.url, dist_km, mins)

        # Send with inline keyboard buttons
        msg_id = send_with_buttons(msg, tracking_id)
        if msg_id:
            tracker_set_msg_id(conn, tracking_id, msg_id)

        mark_seen(conn, seen_key, "solo")
        new_count += 1
        logger.info("Alerted: %s | %.1fkm | %s min (%s)",
                    listing.address[:50], dist_km,
                    f"{mins:.0f}" if mins else "?", src)

    if new_count == 0:
        logger.info("No new listings this cycle.")
    else:
        logger.info("%d new listings sent to Telegram.", new_count)
    logger.info("Cycle done.\n")


def main():
    conn = get_connection(DB_PATH)
    init_db(conn)

    # Start button/command handler in background
    start_polling(conn)

    _tg_send(
        f"🏠 *Rental Monitor started*\n"
        f"Searching {PROPERTY_LABEL} in {CITY} — within {MAX_RADIUS_KM:.0f}km\n"
        f"Tap *⭐ / 📞 / 👎* on any listing to track it.\n"
        f"Send */summary* anytime to see your tracker."
    )
    logger.info("Monitor started. Scanning every %ds.", CHECK_INTERVAL_SECONDS)

    try:
        run_cycle(conn)
    except Exception:
        logger.exception("Error in first cycle")

    while True:
        time.sleep(CHECK_INTERVAL_SECONDS)
        try:
            run_cycle(conn)
        except Exception:
            logger.exception("Unhandled error in cycle — retrying next interval")


if __name__ == "__main__":
    main()
