"""Pending-alerts retry + prune policy."""
import json
import pytest
import pytest_asyncio

from src.models import Listing, RunStats
from src.pipeline.prune import enqueue_pending, process_pending, prune
from src.state.db import connect, migrate


DAY = 86400


def _canonical(price: int = 10000) -> str:
    return Listing(
        id="x", source="sulekha", title="1 BHK",
        address="Pallavaram, Chennai", price=price,
        url="https://x.test/1", fingerprint="fp1",
    ).model_dump_json()


@pytest_asyncio.fixture
async def db(tmp_path):
    async with connect(tmp_path / "t.db") as conn:
        await migrate(conn)
        yield conn


@pytest.mark.asyncio
async def test_process_pending_delivers_and_marks_alerted(db):
    now = 1_700_000_000
    # Seed a listing and a pending row pointing at it
    await db.execute(
        "INSERT INTO listings (fingerprint, first_seen, last_seen, sources, canonical) "
        "VALUES ('fp1', ?, ?, '[]', ?)", (now - DAY, now - DAY, _canonical()))
    await enqueue_pending(db, "fp1", now - 3600)
    await db.commit()

    async def alert(_l, _s):
        return 9999

    delivered = await process_pending(db, alert, RunStats(started_at=now), now)
    assert delivered == 1
    row = await (await db.execute(
        "SELECT alerted_at, msg_id FROM listings WHERE fingerprint = 'fp1'"
    )).fetchone()
    assert row == (now, 9999)
    pending = await (await db.execute(
        "SELECT COUNT(*) FROM pending_alerts")).fetchone()
    assert pending[0] == 0


@pytest.mark.asyncio
async def test_process_pending_increments_retry_on_failure(db):
    now = 1_700_000_000
    await db.execute(
        "INSERT INTO listings (fingerprint, first_seen, last_seen, sources, canonical) "
        "VALUES ('fp1', ?, ?, '[]', ?)", (now - DAY, now - DAY, _canonical()))
    await enqueue_pending(db, "fp1", now - 3600)
    await db.commit()

    async def alert(_l, _s):
        return None

    delivered = await process_pending(db, alert, RunStats(started_at=now), now)
    assert delivered == 0
    rc, = await (await db.execute(
        "SELECT retry_count FROM pending_alerts WHERE fingerprint = 'fp1'"
    )).fetchone()
    assert rc == 1


@pytest.mark.asyncio
async def test_process_pending_drops_after_max_retries(db):
    now = 1_700_000_000
    await db.execute(
        "INSERT INTO listings (fingerprint, first_seen, last_seen, sources, canonical) "
        "VALUES ('fp1', ?, ?, '[]', ?)", (now - DAY, now - DAY, _canonical()))
    await db.execute(
        "INSERT INTO pending_alerts (fingerprint, queued_at, retry_count) "
        "VALUES ('fp1', ?, 47)", (now - 3600,))
    await db.commit()

    async def alert(_l, _s):
        return None

    await process_pending(db, alert, RunStats(started_at=now), now)
    n, = await (await db.execute(
        "SELECT COUNT(*) FROM pending_alerts")).fetchone()
    assert n == 0


@pytest.mark.asyncio
async def test_prune_drops_stale_rows(db):
    now = 1_700_000_000
    # listings: one stale unalerted (60d+), one stale alerted (60d+ but <180d),
    # one ancient (180d+, alerted), one fresh.
    await db.execute(
        "INSERT INTO listings VALUES (?, ?, ?, '[]', ?, ?, ?)",
        ("stale_unalerted", now - 70*DAY, now - 70*DAY, _canonical(), None, None))
    await db.execute(
        "INSERT INTO listings VALUES (?, ?, ?, '[]', ?, ?, ?)",
        ("stale_alerted", now - 70*DAY, now - 70*DAY, _canonical(), now - 70*DAY, 1))
    await db.execute(
        "INSERT INTO listings VALUES (?, ?, ?, '[]', ?, ?, ?)",
        ("ancient", now - 200*DAY, now - 200*DAY, _canonical(), now - 200*DAY, 1))
    await db.execute(
        "INSERT INTO listings VALUES (?, ?, ?, '[]', ?, ?, ?)",
        ("fresh", now - DAY, now - DAY, _canonical(), now - DAY, 1))
    # 110 run rows — keep latest 100
    for i in range(110):
        await db.execute(
            "INSERT INTO runs (started_at,duration_ms,raw_count,after_filter,"
            "after_dedup,alerted,per_source,breaker_open) VALUES (?,1,0,0,0,0,'{}','[]')",
            (now - i,))
    # travel_cache: old + fresh
    await db.execute(
        "INSERT INTO travel_cache VALUES ('k_old', 10.0, 'heuristic', ?)",
        (now - 40*DAY,))
    await db.execute(
        "INSERT INTO travel_cache VALUES ('k_new', 10.0, 'heuristic', ?)",
        (now - DAY,))
    # pending: one expired
    await db.execute(
        "INSERT INTO pending_alerts (fingerprint, queued_at, retry_count) "
        "VALUES ('fresh', ?, 49)", (now - DAY,))
    await db.commit()

    await prune(db, now)

    listings = {r[0] for r in await (await db.execute(
        "SELECT fingerprint FROM listings")).fetchall()}
    assert listings == {"stale_alerted", "fresh"}

    nruns, = await (await db.execute("SELECT COUNT(*) FROM runs")).fetchone()
    assert nruns == 100

    tcache = {r[0] for r in await (await db.execute(
        "SELECT cache_key FROM travel_cache")).fetchall()}
    assert tcache == {"k_new"}

    npending, = await (await db.execute(
        "SELECT COUNT(*) FROM pending_alerts")).fetchone()
    assert npending == 0
