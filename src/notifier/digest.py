"""Daily digest — top-5 listings + per-source health + silent-source warning.

Called from ``run_once.py --digest`` (GitHub Action ``digest.yml``)."""
from __future__ import annotations
import asyncio
import json
import logging
import time
from pathlib import Path

import aiosqlite

from src.models import Listing
from src.pipeline.enrich import is_priority
from src.pipeline.rank import fit_score
from src.state.db import connect, migrate

logger = logging.getLogger("digest")

DAY = 86400
THREE_HOURS = 3 * 3600

_HEALTH_OK = "✅"
_HEALTH_WARN = "⚠️"
_HEALTH_BAD = "❌"


async def _top_listings(db: aiosqlite.Connection, now_ts: int,
                         limit: int = 5) -> list[tuple[int, Listing, int]]:
    """Return ``[(score, listing, confirm_count)]`` from the last 24h."""
    from config import MAX_RENT, MIN_RENT
    rows = await (await db.execute(
        "SELECT canonical, first_seen, sources FROM listings "
        "WHERE last_seen >= ?", (now_ts - DAY,))).fetchall()
    out: list[tuple[int, Listing, int]] = []
    for canonical, first_seen, sources_json in rows:
        try:
            l = Listing.model_validate_json(canonical)
        except Exception:
            continue
        try:
            confirm = len(json.loads(sources_json))
        except Exception:
            confirm = 1
        score = fit_score(
            l, travel_min=None, first_seen_ts=first_seen, now_ts=now_ts,
            confirm_count=confirm, priority=is_priority(l),
            max_rent=MAX_RENT, min_rent=MIN_RENT,
        )
        out.append((score, l, confirm))
    out.sort(key=lambda x: x[0], reverse=True)
    return out[:limit]


async def _per_source_health(
    db: aiosqlite.Connection, now_ts: int,
) -> tuple[dict[str, str], list[str]]:
    """Return (per_source_emoji, silent_warnings).

    Health rules (over the last 24 ``runs``):
      - ✅ scraped > 0 in ≥ 50% of cycles AND errored = 0 in ≥ 80% of cycles
      - ⚠️ otherwise but not all-zero
      - ❌ scraped == 0 in every cycle
    """
    rows = await (await db.execute(
        "SELECT started_at, per_source FROM runs "
        "WHERE started_at >= ? ORDER BY started_at DESC LIMIT 24",
        (now_ts - DAY,))).fetchall()
    per_source: dict[str, list[dict]] = {}
    silent_window: dict[str, list[dict]] = {}
    for started_at, per_src_json in rows:
        try:
            per_src = json.loads(per_src_json) or {}
        except Exception:
            continue
        for name, stats in per_src.items():
            per_source.setdefault(name, []).append(stats)
            if started_at >= now_ts - THREE_HOURS:
                silent_window.setdefault(name, []).append(stats)
    health: dict[str, str] = {}
    for name, runs in per_source.items():
        n = len(runs)
        scraped_ok = sum(1 for r in runs if (r.get("scraped") or 0) > 0)
        errored = sum(1 for r in runs if (r.get("errored") or 0) > 0)
        if scraped_ok == 0:
            health[name] = _HEALTH_BAD
        elif scraped_ok / n >= 0.5 and errored / n <= 0.2:
            health[name] = _HEALTH_OK
        else:
            health[name] = _HEALTH_WARN
    silent: list[str] = []
    for name, runs in silent_window.items():
        zero_cycles = sum(1 for r in runs if (r.get("scraped") or 0) == 0)
        if zero_cycles >= 3:
            silent.append(name)
    return health, silent


def _format(top: list[tuple[int, Listing, int]],
            health: dict[str, str], silent: list[str]) -> str:
    lines = ["📋 *Daily rental digest*", ""]
    if not top:
        lines.append("_No new listings in the last 24h._")
    else:
        lines.append(f"Top {len(top)} by fit score (last 24h):")
        for score, l, confirm in top:
            seen_str = f"  ·  seen on {confirm}" if confirm > 1 else ""
            lines.append(
                f"• *₹{l.price:,}* — {l.address}{seen_str}\n"
                f"   [{l.source}] score {score}  ·  {l.url}")
    lines.append("")
    if health:
        lines.append("Source health (24h):")
        for name in sorted(health):
            lines.append(f"{health[name]} {name}")
    for name in silent:
        lines.append(f"{_HEALTH_WARN} {name} has been silent 3h — may be blocked")
    return "\n".join(lines)


async def run_digest(db_path: Path) -> None:
    now_ts = int(time.time())
    async with connect(db_path) as db:
        await migrate(db)
        top = await _top_listings(db, now_ts)
        health, silent = await _per_source_health(db, now_ts)
    msg = _format(top, health, silent)
    # Send as a regular text (no tracking buttons for the digest)
    from src.notifier.telegram import _BASE, _chat_id, _token
    import requests
    try:
        requests.post(_BASE.format(token=_token(), method="sendMessage"),
                      json={"chat_id": _chat_id(), "text": msg,
                            "parse_mode": "Markdown",
                            "disable_web_page_preview": True},
                      timeout=10).raise_for_status()
    except Exception:
        logger.exception("digest send failed")
