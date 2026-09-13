"""
Telegram notification module — 100% free, no per-message cost.

Setup (one-time, takes 2 minutes):
  1. Open Telegram → search @BotFather → send /newbot
  2. Pick any name and username (e.g. HarshRentalBot)
  3. Copy the token it gives you  →  add to .env as TELEGRAM_BOT_TOKEN
  4. Search your new bot in Telegram → send it any message (e.g. "hi")
  5. Run:  python setup_telegram.py   →  it prints your TELEGRAM_CHAT_ID
  6. Add TELEGRAM_CHAT_ID=<number> to .env
"""

import logging
import os
import requests
from datetime import datetime, timezone
from src.models import Listing
from src.filters.distance_filter import is_priority_locality

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


def _configured() -> bool:
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


def format_message(listing: Listing, zone: str, distance_km: float | None, mode: str = "solo") -> str:
    """
    mode = "solo"  → single person listing (🏠)
    mode = "group" → shared listing for group search (🏘) — use format_group_message instead
    """
    dist_str = f"{distance_km:.1f}km" if distance_km is not None else "dist unknown"
    priority = " ⭐ PRIORITY AREA" if is_priority_locality(listing.address) else ""
    broker_line = "No broker" if "nobroker" in listing.source.lower() else "Check for broker"
    bachelor = "Bachelors OK" if listing.bachelors_allowed else "Occupancy unspecified"

    # Solo listings use house emoji; visually distinct from group listings
    header_emoji = "🏠"
    label = "SOLO — FOR YOU ONLY"

    lines = [
        f"{header_emoji} *{label} | {zone}* ({dist_str} from your office)",
        "─────────────────────────",
        f"📍 {listing.address}{priority}",
        f"💰 ₹{listing.price:,}/month | {listing.furnishing.title()}",
        f"{bachelor} | {broker_line}",
    ]

    if listing.rating is not None:
        review = f' — "{listing.review_snippet}"' if listing.review_snippet else ""
        lines.append(f"⭐ {listing.rating}/5{review}")

    if listing.lat is not None and listing.lng is not None:
        maps_url = f"https://maps.google.com/?q={listing.lat},{listing.lng}"
        lines.append(f"🗺 [View on Maps]({maps_url})")

    lines += [
        f"🌐 Source: {listing.source.title()}",
        f"🔗 [Open listing]({listing.url})",
        "",
        f"_Found: {datetime.now(timezone.utc).strftime('%H:%M, %d %b %Y')} UTC_",
    ]
    return "\n".join(lines)


def send_alert(listing: Listing, zone: str, distance_km: float | None) -> bool:
    """Send a Telegram alert. Returns True on success."""
    if not _configured():
        logger.warning("Telegram not configured — skipping (set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID)")
        return False

    token   = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    text    = format_message(listing, zone, distance_km)

    url = TELEGRAM_API.format(token=token, method="sendMessage")
    try:
        r = requests.post(url, json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": False,
        }, timeout=10)
        r.raise_for_status()
        logger.info("Telegram alert sent for %s/%s", listing.source, listing.id)
        return True
    except Exception:
        logger.exception("Telegram send failed for %s/%s", listing.source, listing.id)
        return False


def send_text(message: str) -> bool:
    """Send a plain text message (for health checks, summaries, etc.)."""
    if not _configured():
        return False

    token   = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = TELEGRAM_API.format(token=token, method="sendMessage")
    try:
        r = requests.post(url, json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown",
        }, timeout=10)
        r.raise_for_status()
        return True
    except Exception:
        logger.exception("Telegram send_text failed")
        return False


def health_check() -> bool:
    """Send a startup check message. Returns True if delivered."""
    return send_text(
        "🏠 *Rental Monitor started*\n"
        "Watching for 1BHK listings near Chromepet (5–10km radius).\n"
        "You will be notified for every new match."
    )
