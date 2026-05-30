"""v2 alert function — wraps the sync ``tracker_bot.send_with_buttons``.

The engine awaits ``alert(listing, stats) -> int | None``. The underlying
HTTP call is synchronous, so we hop to a thread to keep the event loop free.
"""
from __future__ import annotations
import asyncio
import hashlib

from src.models import Listing, RunStats


def _tracking_id(l: Listing) -> str:
    seed = (l.fingerprint or l.url or l.id).encode()
    return hashlib.sha256(seed).hexdigest()[:16]


def _format(l: Listing) -> str:
    price = f"₹{l.price:,}"
    title = l.title or l.address
    lines = [
        f"🏠 *{title}*",
        f"📍 {l.address}",
        f"💰 {price}/mo  ·  *{l.furnishing}*  ·  via {l.source}",
        f"🔗 {l.url}",
    ]
    if l.also_seen_on:
        lines.append("Also: " + ", ".join(l.also_seen_on[:3]))
    return "\n".join(lines)


def _send(l: Listing) -> int | None:
    from src.notifier.telegram import send_with_buttons
    return send_with_buttons(_format(l), _tracking_id(l))


async def alert(l: Listing, _stats: RunStats) -> int | None:
    return await asyncio.to_thread(_send, l)
