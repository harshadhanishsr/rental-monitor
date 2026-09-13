import json
import pytest
import pytest_asyncio

from src.models import Listing
from src.notifier.digest import _per_source_health, _top_listings, _format
from src.state.db import connect, migrate

DAY = 86400


def _canonical(price=10000, source="sulekha") -> str:
    return Listing(
        id="x", source=source, title="1 BHK",
        address="Pallavaram, Chennai", price=price,
        url=f"https://x.test/{price}", fingerprint=f"fp_{price}",
        lat=12.97, lng=80.18,
    ).model_dump_json()


@pytest_asyncio.fixture
async def db(tmp_path):
    async with connect(tmp_path / "t.db") as conn:
        await migrate(conn)
        yield conn


@pytest.mark.asyncio
async def test_top_listings_returns_within_last_24h_sorted(db):
    now = 1_700_000_000
    await db.execute(
        "INSERT INTO listings VALUES (?,?,?, '[\"sulekha\"]', ?, NULL, NULL)",
        ("fp_a", now - DAY//2, now - DAY//2, _canonical(price=14000)))
    await db.execute(
        "INSERT INTO listings VALUES (?,?,?, '[\"sulekha\",\"99acres\"]', ?, NULL, NULL)",
        ("fp_b", now - DAY//4, now - DAY//4, _canonical(price=10000)))
    await db.execute(
        "INSERT INTO listings VALUES (?,?,?, '[]', ?, NULL, NULL)",
        ("fp_old", now - 5*DAY, now - 5*DAY, _canonical(price=12000)))
    await db.commit()

    top = await _top_listings(db, now)
    # canonical's own fingerprint comes from _canonical(price=...)
    assert {l.fingerprint for _, l, _ in top} == {"fp_14000", "fp_10000"}
    # The 10000-price listing has confirm=2 and lower price -> outscores 14000
    assert top[0][1].fingerprint == "fp_10000"


@pytest.mark.asyncio
async def test_per_source_health_classifies(db):
    now = 1_700_000_000
    per_src_healthy = json.dumps({"sulekha": {"scraped": 5, "errored": 0}})
    per_src_broken  = json.dumps({"olx": {"scraped": 0, "errored": 1}})
    for i in range(10):
        await db.execute(
            "INSERT INTO runs (started_at,duration_ms,raw_count,after_filter,"
            "after_dedup,alerted,per_source,breaker_open) "
            "VALUES (?,1,0,0,0,0,?,'[]')",
            (now - i*3600, per_src_healthy))
        await db.execute(
            "INSERT INTO runs (started_at,duration_ms,raw_count,after_filter,"
            "after_dedup,alerted,per_source,breaker_open) "
            "VALUES (?,1,0,0,0,0,?,'[]')",
            (now - i*3600, per_src_broken))
    await db.commit()

    health, silent = await _per_source_health(db, now)
    assert health["sulekha"] == "✅"
    assert health["olx"] == "❌"
    # 3 most recent olx cycles all show scraped == 0 -> silent
    assert "olx" in silent
    assert "sulekha" not in silent


def test_format_handles_empty_top():
    msg = _format([], {"sulekha": "✅"}, [])
    assert "No new listings" in msg
    assert "sulekha" in msg
