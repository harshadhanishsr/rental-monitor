"""
Group house-hunting search.

Each person enters their workplace location and transport mode in config.py
under GROUP_MEMBERS. This script finds listings at the geographically and
temporally fairest location for the whole group, ranked by how equitably
everyone can reach their office — in real travel time, not just distance.

Usage:
    python group_search.py

For accurate transit times set GOOGLE_MAPS_API_KEY in your .env file.
Without it, travel times are estimated from distance + mode speed heuristics.
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
    GROUP_MEMBERS,
    MAX_COMMUTE_PER_PERSON_MINUTES,
    MAX_COMMUTE_PER_PERSON_KM,
    PROPERTY_LABEL, CITY,
)
from src.db import init_db, get_connection
from src.scheduler import run_all_scrapers, apply_property_filter
from src.filters.distance_filter import geocode_listing, is_priority_locality
from src.group_optimizer import (
    optimal_search_centre,
    score_listing_for_group,
    passes_group_filter,
    format_group_commutes,
)
from src.notifier import telegram_bot as _tg

DB_PATH = os.environ.get("DB_PATH", "data/rental_monitor.db")
_USE_GMAPS = bool(os.environ.get("GOOGLE_MAPS_API_KEY", ""))


def _group_alert(listing, score) -> str:
    from datetime import datetime, timezone
    priority = " ⭐ PRIORITY AREA" if is_priority_locality(listing.address) else ""
    broker_line = "No broker" if "nobroker" in listing.source.lower() else "Check for broker"
    est_note = " (~estimated)" if any(m.time_source == "heuristic" for m in score.members) else ""

    lines = [
        f"🏘 *GROUP — {PROPERTY_LABEL}* | Worst commute: {score.max_minutes:.0f} min{est_note}",
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

    print(f"\n{'='*62}")
    print(f"  GROUP SEARCH for {len(GROUP_MEMBERS)} people")
    for m in GROUP_MEMBERS:
        mode = m.get("transport", "driving")
        print(f"  · {m['name']:12s} ({mode}) — office at ({m['office_lat']:.4f}, {m['office_lng']:.4f})")
    api_status = "Google Maps API ✓" if _USE_GMAPS else "heuristic estimates (no GOOGLE_MAPS_API_KEY)"
    print(f"  Travel times: {api_status}")
    print(f"{'='*62}\n")

    centre_lat, centre_lng = optimal_search_centre(GROUP_MEMBERS)
    print(f"Optimal search centre: ({centre_lat:.4f}, {centre_lng:.4f})")
    print(f"Max commute per person: {MAX_COMMUTE_PER_PERSON_MINUTES} min\n")

    conn = get_connection(DB_PATH)
    init_db(conn)

    logger.info("Scraping all sources…")
    raw = run_all_scrapers()
    filtered = apply_property_filter(raw)
    logger.info("After property filter: %d listings", len(filtered))

    results = []
    for listing in filtered:
        if listing.lat and listing.lng:
            lat, lng = listing.lat, listing.lng
        else:
            coords = geocode_listing(listing.address, conn)
            if not coords:
                continue
            lat, lng = coords
            listing.lat, listing.lng = lat, lng

        score = score_listing_for_group(lat, lng, GROUP_MEMBERS, conn)

        if not passes_group_filter(score, MAX_COMMUTE_PER_PERSON_MINUTES, MAX_COMMUTE_PER_PERSON_KM):
            continue

        results.append((listing, score))

    if not results:
        print("No listings found within the per-person commute limit.")
        print(f"Try increasing MAX_COMMUTE_PER_PERSON_MINUTES (currently {MAX_COMMUTE_PER_PERSON_MINUTES}) in config.py")
        return

    # Sort by fairness score (min worst commute + variance)
    results.sort(key=lambda x: x[1].fairness_score)

    print(f"{'='*62}")
    print(f"  {len(results)} listings — sorted by fairness (best first)")
    print(f"{'='*62}\n")

    for i, (listing, score) in enumerate(results, 1):
        print(f"{i:>2}. {listing.title[:55]}")
        print(f"     📍 {listing.address}")
        print(f"     💰 ₹{listing.price:,}/month | {listing.furnishing}")
        print(f"     👥 ", end="")
        parts = []
        for m in score.members:
            est = "~" if m.time_source == "heuristic" else ""
            parts.append(f"{m.name}: {est}{m.travel_minutes:.0f}min")
        print("  |  ".join(parts))
        print(f"     📊 Avg: {score.avg_minutes:.0f}min | Worst: {score.max_minutes:.0f}min | Score: {score.fairness_score:.1f}")
        print(f"     🔗 {listing.url[:70]}")
        if listing.lat and listing.lng:
            print(f"     🗺  https://maps.google.com/?q={listing.lat},{listing.lng}")
        print()

    top = results[:8]
    use_telegram = bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))

    if use_telegram:
        names = " + ".join(m["name"] for m in GROUP_MEMBERS)
        est_note = " (estimated)" if not _USE_GMAPS else ""
        header = (
            f"🏘 *Group Search: {names}*\n"
            f"{len(results)} listings | max {MAX_COMMUTE_PER_PERSON_MINUTES} min/person{est_note}\n"
            f"Sorted by fairness (lowest worst-commute first):"
        )
        _tg.send_text(header)
        token   = os.environ["TELEGRAM_BOT_TOKEN"]
        chat_id = os.environ["TELEGRAM_CHAT_ID"]
        import requests as _req
        for listing, score in top:
            msg = _group_alert(listing, score)
            try:
                _req.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": msg,
                          "parse_mode": "Markdown", "disable_web_page_preview": False},
                    timeout=10,
                ).raise_for_status()
            except Exception:
                logger.exception("Failed to send group alert for %s", listing.id)
        print(f"Sent {len(top)} results to Telegram.")
    else:
        print("Tip: set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID in .env to get these on your phone.")


if __name__ == "__main__":
    main()
