"""DB hygiene — pending-alerts retry + prune policy (spec Section 5)."""
from __future__ import annotations
import json
import logging
from typing import Awaitable, Callable

import aiosqlite

from src.models import Listing, RunStats

logger = logging.getLogger("prune")

_MAX_RETRIES = 48
_PENDING_BATCH = 25

DAY = 86400
SIXTY_D = 60 * DAY
ONE_EIGHTY_D = 180 * DAY
THIRTY_D = 30 * DAY


async def process_pending(
    db: aiosqlite.Connection,
    alert_fn: Callable[[Listing, RunStats], Awaitable[int | None]],
    stats: RunStats,
    now_ts: int,
) -> int:
    """Retry up to ``_PENDING_BATCH`` queued alerts. Returns # delivered."""
    rows = await (await db.execute(
        "SELECT p.pending_id, p.fingerprint, p.retry_count, l.canonical "
        "FROM pending_alerts p JOIN listings l ON l.fingerprint = p.fingerprint "
        "ORDER BY p.queued_at LIMIT ?", (_PENDING_BATCH,))).fetchall()
    delivered = 0
    for pending_id, fp, retry_count, canonical in rows:
        try:
            l = Listing.model_validate_json(canonical)
        except Exception as e:
            logger.warning("pending row %d unreadable: %s — dropping", pending_id, e)
            await db.execute("DELETE FROM pending_alerts WHERE pending_id = ?",
                             (pending_id,))
            continue
        try:
            msg_id = await alert_fn(l, stats)
        except Exception as e:
            msg_id, err = None, str(e)[:200]
        else:
            err = None
        if msg_id is not None:
            await db.execute("DELETE FROM pending_alerts WHERE pending_id = ?",
                             (pending_id,))
            await db.execute(
                "UPDATE listings SET alerted_at = ?, msg_id = ? WHERE fingerprint = ?",
                (now_ts, msg_id, fp))
            delivered += 1
        else:
            next_retry = retry_count + 1
            if next_retry >= _MAX_RETRIES:
                await db.execute(
                    "DELETE FROM pending_alerts WHERE pending_id = ?",
                    (pending_id,))
            else:
                await db.execute(
                    "UPDATE pending_alerts SET retry_count = ?, last_error = ? "
                    "WHERE pending_id = ?",
                    (next_retry, err, pending_id))
    await db.commit()
    return delivered


async def enqueue_pending(db: aiosqlite.Connection, fingerprint: str,
                           queued_at: int, err: str | None = None) -> None:
    await db.execute(
        "INSERT INTO pending_alerts (fingerprint, queued_at, retry_count, last_error) "
        "VALUES (?, ?, 0, ?)",
        (fingerprint, queued_at, err))


async def prune(db: aiosqlite.Connection, now_ts: int) -> None:
    """Drop stale listings/runs/travel_cache/pending_alerts; VACUUM if > 5MB."""
    await db.execute(
        "DELETE FROM listings WHERE last_seen < ? AND alerted_at IS NULL",
        (now_ts - SIXTY_D,))
    await db.execute(
        "DELETE FROM listings WHERE last_seen < ?",
        (now_ts - ONE_EIGHTY_D,))
    await db.execute(
        "DELETE FROM runs WHERE run_id NOT IN "
        "(SELECT run_id FROM runs ORDER BY run_id DESC LIMIT 100)")
    await db.execute(
        "DELETE FROM travel_cache WHERE cached_at < ?", (now_ts - THIRTY_D,))
    await db.execute(
        "DELETE FROM pending_alerts WHERE retry_count >= ?", (_MAX_RETRIES,))
    await db.commit()
    row = await (await db.execute(
        "SELECT page_count*page_size FROM pragma_page_count, pragma_page_size"
    )).fetchone()
    size = row[0] if row else 0
    if size > 5 * 1024 * 1024:
        await db.execute("VACUUM")
