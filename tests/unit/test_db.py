import pytest
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
