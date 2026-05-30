from __future__ import annotations
import aiosqlite
from contextlib import asynccontextmanager
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


@asynccontextmanager
async def connect(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(db_path)
    await conn.execute("PRAGMA foreign_keys = ON")
    await conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
    finally:
        await conn.commit()
        await conn.close()


async def _current_version(conn: aiosqlite.Connection) -> int:
    try:
        row = await (await conn.execute(
            "SELECT MAX(version) FROM schema_version")).fetchone()
        return row[0] or 0
    except aiosqlite.OperationalError:
        return 0


async def migrate(conn: aiosqlite.Connection) -> None:
    current = await _current_version(conn)
    for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = int(sql_file.stem.split("_")[0])
        if version <= current:
            continue
        await conn.executescript(sql_file.read_text())
        await conn.commit()
