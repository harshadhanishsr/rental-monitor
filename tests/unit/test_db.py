import pytest
import aiosqlite
from pathlib import Path
from src.state.db import connect, migrate


@pytest.mark.asyncio
async def test_migrate_creates_listings_table(tmp_path: Path):
    db = tmp_path / "t.db"
    async with connect(db) as conn:
        await migrate(conn)
        rows = await (await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
    names = {r[0] for r in rows}
    assert {"listings", "tracker", "runs", "travel_cache",
            "pending_alerts", "schema_version"} <= names


@pytest.mark.asyncio
async def test_migrate_is_idempotent(tmp_path: Path):
    db = tmp_path / "t.db"
    async with connect(db) as conn:
        await migrate(conn)
        await migrate(conn)  # second run must not error
        row = await (await conn.execute(
            "SELECT COUNT(*) FROM schema_version")).fetchone()
        assert row[0] == 1


@pytest.mark.asyncio
async def test_foreign_keys_enforced(tmp_path: Path):
    db = tmp_path / "t.db"
    async with connect(db) as conn:
        await migrate(conn)
        # pending_alerts.fingerprint references listings.fingerprint; bogus value must raise
        with pytest.raises(aiosqlite.IntegrityError):
            await conn.execute(
                "INSERT INTO pending_alerts (fingerprint, queued_at) "
                "VALUES ('does-not-exist', 0)")
            await conn.commit()
