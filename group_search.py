"""
Group house-hunting search.

Each person enters their workplace location in config.py → GROUP_MEMBERS.
This script finds listings at the geographically fairest location for the
whole group, ranked by how equitably everyone can reach their office.

Usage:
    python group_search.py
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
logger = logging.getLogger("group_search")

from config import (
    GROUP_MEMBERS, MAX_COMMUTE_PER_PERSON_KM, MAX_RADIUS_KM,
    MAX_RENT, PROPERTY_LABEL, CITY,
)
from src.db import init_db, get_connection
from src.scheduler import run_all_scrapers, apply_property_filter
from src.filters.distance_filter import geocode_listing
from src.group_optimizer import (
    optimal_search_centre,
    score_listing_for_group,
    passes_group_filter,
    format_group_commutes,
)
from src.notifier import telegram_bot as _tg

DB_PATH = os.environ.get("DB_PATH", "data/rental_monitor.db")


def _group_alert(listing, score) -> str:
    from src.filters.distance_filter import is_priority_locality
    from datetime import datetime, timezone

    priority = " ⭐ PRIORITY AREA" if is_priority_locality(listing.address) else ""
    broker_line = "No broker" if "nobroker" in listing.source.lower() else "Check for broker"

    lines = [
        f"🏘 *GROUP SEARCH — {PROPERTY_LABEL}* | {score.max_km:.1f} km worst commute",
        "",
        f"📍 {listing.address}{priority}",
        f"💰 ₹{listing.price:,}/month | {listing.furnishing.title()}",
        f"{broker_line}",
        "",
        format_group_commutes(score),
    ]

    if listing.lat and listing.lng:
        maps_url = f"https://maps.google.com/?q={listing.lat},{listing.lng}"
        lines.append(f"\n🗺 [View on Maps]({maps_url})")

    lines += [
        f"🌐 {listing.source.title()}",
        f"🔗 [Open listing]({listing.url})",
        "",
        f"_Found: {datetime.now(timezone.utc).strftime('%H:%M, %d %b %Y')} UTC_",
    ]
    return "\n".join(lines)


def main():
    if not GROUP_MEMBERS:
        print("No GROUP_MEMBERS defined in config.py — add at least 2 people.")
        return

    print(f"\n{'='*60}")
    print(f"  GROUP SEARCH for {len(GROUP_MEMBERS)} people")
    for m in GROUP_MEMBERS:
        print(f"  · {m['name']} — office at ({m['office_lat']:.4f}, {m['office_lng']:.4f})")
    print(f"{'='*60}\n")

    # Find the geometric median of all office locations
    centre_lat, centre_lng = optimal_search_centre(GROUP_MEMBERS)
    print(f"Optimal search centre: ({centre_lat:.4f}, {centre_lng:.4f})")
    print(f"Max commute per person: {MAX_COMMUTE_PER_PERSON_KM} km\n")

    conn = get_connection(DB_PATH)
    init_db(conn)

    logger.info("Scraping all sources…")
    raw = run_all_scrapers()
    filtered = apply_property_filter(raw)
    logger.info("After property filter: %d listings", len(filtered))

    # Geocode each listing and score for the group
    results = []
    for listing in filtered:
        # Use pre-set coordinates if available, else geocode
        if listing.lat and listing.lng:
            lat, lng = listing.lat, listing.lng
        else:
            coords = geocode_listing(listing.address, conn)
            if not coords:
                continue
            lat, lng = coords
            listing.lat, listing.lng = lat, lng

        score = score_listing_for_group(lat, lng, GROUP_MEMBERS)

        # Filter: no one commutes more than the per-person limit
        if not passes_group_filter(score, MAX_COMMUTE_PER_PERSON_KM):
            continue

        results.append((listing, score))

    if not results:
        print("No listings found within the per-person commute limit.")
        print(f"Try increasing MAX_COMMUTE_PER_PERSON_KM (currently {MAX_COMMUTE_PER_PERSON_KM} km) in config.py")
        return

    # Sort by fairness score (minimise max commute + variance)
    results.sort(key=lambda x: x[1].fairness_score)

    print(f"{'='*60}")
    print(f"  {len(results)} listings — sorted by fairness (best first)")
    print(f"{'='*60}\n")

    for i, (listing, score) in enumerate(results, 1):
        print(f"{i:>2}. {listing.title[:55]}")
        print(f"     📍 {listing.address}")
        print(f"     💰 ₹{listing.price:,}/month | {listing.furnishing}")
        print(f"     👥 Commutes: ", end="")
        commutes = ", ".join(f"{m.name} {m.distance_km:.1f}km" for m in score.members)
        print(commutes)
        print(f"     📊 Avg: {score.avg_km:.1f}km | Max: {score.max_km:.1f}km | Score: {score.fairness_score:.2f}")
        print(f"     🔗 {listing.url[:70]}")
        if listing.lat and listing.lng:
            print(f"     🗺  https://maps.google.com/?q={listing.lat},{listing.lng}")
        print()

    # Send top results via Telegram
    top = results[:8]
    use_telegram = bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))

    if use_telegram:
        names = " + ".join(m["name"] for m in GROUP_MEMBERS)
        header = (
            f"🏘 *Group Search: {names}*\n"
            f"{len(results)} listings found | max {MAX_COMMUTE_PER_PERSON_KM:.0f}km per person\n"
            f"Sorted by fairness (lowest max commute first):"
        )
        _tg.send_text(header)
        for listing, score in top:
            msg = _group_alert(listing, score)
            token   = os.environ["TELEGRAM_BOT_TOKEN"]
            chat_id = os.environ["TELEGRAM_CHAT_ID"]
            import requests as _req
            _req.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown",
                      "disable_web_page_preview": False},
                timeout=10,
            )
        print(f"Sent {len(top)} results to Telegram.")
    else:
        print("Tip: set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID in .env to get these on your phone.")


if __name__ == "__main__":
    main()
