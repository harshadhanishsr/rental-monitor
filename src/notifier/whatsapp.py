import logging
import os
from datetime import datetime, timezone
from twilio.rest import Client
from src.models import Listing

logger = logging.getLogger(__name__)


def _get_client() -> Client:
    return Client(
        os.environ["TWILIO_ACCOUNT_SID"],
        os.environ["TWILIO_AUTH_TOKEN"],
    )


def format_message(listing: Listing, zone: str, distance_km: float | None) -> str:
    if distance_km is not None:
        header = f"NEW 1BHK — {zone} ({distance_km:.1f}km from office)"
    else:
        header = f"NEW 1BHK — {zone}"

    broker_line = "No broker" if "nobroker" in listing.source.lower() else "Check for broker"
    bachelor_line = "✅ Bachelors allowed" if listing.bachelors_allowed else "ℹ️ Occupancy unspecified"

    lines = [
        header,
        "",
        f"📍 {listing.address}",
        f"💰 ₹{listing.price:,}/month | {listing.furnishing.title()}",
        f"{bachelor_line} | {broker_line}",
    ]

    if listing.rating is not None:
        review = f' — "{listing.review_snippet}"' if listing.review_snippet else ""
        lines.append(f"⭐ {listing.rating}/5{review}")

    lines += [
        f"🌐 Source: {listing.source.title()}",
        f"🔗 {listing.url}",
        "",
        f"Found at: {datetime.now(timezone.utc).strftime('%H:%M, %d %b %Y')} UTC",
    ]
    return "\n".join(lines)


def send_alert(listing: Listing, zone: str, distance_km: float | None) -> str:
    """Send WhatsApp alert text. Returns Twilio message SID on success.

    Images are sent best-effort via send_images(); call that separately
    after send_alert() if you want to forward listing photos.
    """
    client = _get_client()
    body = format_message(listing, zone, distance_km)
    from_number = os.environ["TWILIO_WHATSAPP_FROM"]
    to_number = os.environ["WHATSAPP_TO"]

    msg = client.messages.create(body=body, from_=from_number, to=to_number)
    return msg.sid


def send_images(listing: Listing) -> None:
    """Send listing images best-effort over WhatsApp. Logs but never raises."""
    client = _get_client()
    from_number = os.environ["TWILIO_WHATSAPP_FROM"]
    to_number = os.environ["WHATSAPP_TO"]

    for image_url in listing.images[:3]:
        try:
            client.messages.create(
                media_url=[image_url],
                from_=from_number,
                to=to_number,
            )
        except Exception:
            logger.warning("Failed to send image %s for listing %s", image_url, listing.id)


def health_check() -> bool:
    """Send a test message. Returns True if delivered, False otherwise."""
    try:
        client = _get_client()
        msg = client.messages.create(
            body="🏠 Rental Monitor is active and watching for listings. (startup check)",
            from_=os.environ["TWILIO_WHATSAPP_FROM"],
            to=os.environ["WHATSAPP_TO"],
        )
        logger.info("Health check passed. SID: %s", msg.sid)
        return True
    except Exception:
        logger.warning(
            "Health check failed — Twilio delivery error. "
            "If your Sandbox session expired, re-send the join message from your phone."
        )
        return False
