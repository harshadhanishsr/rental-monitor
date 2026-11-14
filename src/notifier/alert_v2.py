"""v2 alert function — wraps the sync ``tracker_bot.send_with_buttons``.

The engine awaits ``alert(listing, stats) -> int | None``. The underlying
HTTP call is synchronous, so we hop to a thread to keep the event loop free.
"""
from __future__ import annotations
import asyncio
import hashlib
import re

from haversine import Unit, haversine

from src.models import Listing, RunStats

_BED_RE = re.compile(r"\b(\d)\s*(?:bhk|bedroom|rk)\b", re.I)


def _tracking_id(l: Listing) -> str:
    seed = (l.fingerprint or l.url or l.id).encode()
    return hashlib.sha256(seed).hexdigest()[:16]


def _bedrooms(l: Listing) -> str | None:
    m = _BED_RE.search(l.title or "")
    return f"{m.group(1)} BHK" if m else None


def _distance_km(l: Listing) -> float | None:
    from config import OFFICE_LAT, OFFICE_LNG
    if l.lat is None or l.lng is None:
        return None
    return haversine((OFFICE_LAT, OFFICE_LNG), (l.lat, l.lng), unit=Unit.KILOMETERS)


def _format(l: Listing) -> str:
    price = f"₹{l.price:,}"
    title = l.title or l.address
    parts = [f"💰 {price}/mo"]
    beds = _bedrooms(l)
    if beds:
        parts.append(f"🛏 {beds}")
    parts.append(f"*{l.furnishing}*")
    dist = _distance_km(l)
    if dist is not None:
        parts.append(f"📏 {dist:.1f} km")
    parts.append(f"via {l.source}")
    lines = [
        f"🏠 *{title}*",
        f"📍 {l.address}",
        "  ·  ".join(parts),
        f"🔗 {l.url}",
    ]
    if l.also_seen_on:
        lines.append("Also: " + ", ".join(l.also_seen_on[:3]))
    return "\n".join(lines)


def _send(l: Listing) -> int | None:
    from src.notifier.telegram import send_with_buttons
    photo = l.images[0] if l.images else None
    return send_with_buttons(_format(l), _tracking_id(l), photo_url=photo)


async def alert(l: Listing, _stats: RunStats) -> int | None:
    return await asyncio.to_thread(_send, l)
