import sqlite3
import json
from datetime import datetime, timezone
from src.models import Listing


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS listing_tracker (
            tracking_id  TEXT PRIMARY KEY,
            address      TEXT,
            price        INTEGER,
            url          TEXT,
            dist_km      REAL,
            transit_mins REAL,
            telegram_msg_id INTEGER,
            status       TEXT DEFAULT 'new',
            created_at   INTEGER DEFAULT (strftime('%s','now')),
            updated_at   INTEGER DEFAULT (strftime('%s','now'))
        );

        CREATE TABLE IF NOT EXISTS seen_listings (
            id TEXT NOT NULL,
            source TEXT NOT NULL,
            seen_at TEXT NOT NULL,
            PRIMARY KEY (id, source)
        );

        CREATE TABLE IF NOT EXISTS geocode_cache (
            address_hash TEXT PRIMARY KEY,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            cached_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS pending_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id TEXT NOT NULL,
            source TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            zone TEXT NOT NULL,
            distance_km REAL,
            created_at TEXT NOT NULL,
            retry_count INTEGER DEFAULT 0
        );
    """)
    conn.commit()


def is_seen(conn: sqlite3.Connection, listing_id: str, source: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM seen_listings WHERE id = ? AND source = ?",
        (listing_id, source)
    ).fetchone()
    return row is not None


def mark_seen(conn: sqlite3.Connection, listing_id: str, source: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR IGNORE INTO seen_listings (id, source, seen_at) VALUES (?, ?, ?)",
        (listing_id, source, now)
    )
    conn.commit()


def add_pending_alert(conn: sqlite3.Connection, listing: Listing, zone: str, distance_km: float | None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO pending_alerts (listing_id, source, payload_json, zone, distance_km, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (listing.id, listing.source, listing.to_json(), zone, distance_km, now)
    )
    conn.commit()


def get_pending_alerts(conn: sqlite3.Connection) -> list[tuple[int, Listing, str, float | None]]:
    rows = conn.execute(
        "SELECT id, payload_json, zone, distance_km FROM pending_alerts ORDER BY created_at"
    ).fetchall()
    return [(row[0], Listing.from_json(row[1]), row[2], row[3]) for row in rows]


def resolve_pending_alert(conn: sqlite3.Connection, row_id: int) -> None:
    conn.execute("DELETE FROM pending_alerts WHERE id = ?", (row_id,))
    conn.commit()


def increment_retry(conn: sqlite3.Connection, row_id: int) -> None:
    conn.execute(
        "UPDATE pending_alerts SET retry_count = retry_count + 1 WHERE id = ?",
        (row_id,)
    )
    conn.commit()


def delete_stale_pending(conn: sqlite3.Connection, max_retries: int = 48) -> None:
    conn.execute(
        "DELETE FROM pending_alerts WHERE retry_count >= ?",
        (max_retries,)
    )
    conn.commit()


def cache_geocode(conn: sqlite3.Connection, address_hash: str, lat: float, lng: float) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT OR REPLACE INTO geocode_cache (address_hash, lat, lng, cached_at) VALUES (?, ?, ?, ?)",
        (address_hash, lat, lng, now)
    )
    conn.commit()


def get_cached_geocode(conn: sqlite3.Connection, address_hash: str) -> tuple[float, float] | None:
    row = conn.execute(
        "SELECT lat, lng FROM geocode_cache WHERE address_hash = ?",
        (address_hash,)
    ).fetchone()
    return (row[0], row[1]) if row else None


# ── Listing tracker ───────────────────────────────────────────

def tracker_add(conn, tracking_id, address, price, url, dist_km, transit_mins):
    conn.execute(
        "INSERT OR IGNORE INTO listing_tracker "
        "(tracking_id, address, price, url, dist_km, transit_mins) VALUES (?,?,?,?,?,?)",
        (tracking_id, address, price, url, dist_km, transit_mins),
    )
    conn.commit()


def tracker_set_msg_id(conn, tracking_id, msg_id):
    conn.execute(
        "UPDATE listing_tracker SET telegram_msg_id=? WHERE tracking_id=?",
        (msg_id, tracking_id),
    )
    conn.commit()


def tracker_set_status(conn, tracking_id, status):
    conn.execute(
        "UPDATE listing_tracker SET status=?, updated_at=strftime('%s','now') "
        "WHERE tracking_id=?",
        (status, tracking_id),
    )
    conn.commit()


def tracker_summary(conn) -> dict:
    rows = conn.execute(
        "SELECT status, address, price, url, dist_km, transit_mins, updated_at "
        "FROM listing_tracker WHERE status != 'new' ORDER BY updated_at DESC"
    ).fetchall()
    result = {"shortlisted": [], "contacted": [], "passed": []}
    for r in rows:
        result.get(r["status"], []).append(dict(r))
    return result


def tracker_get(conn, tracking_id):
    return conn.execute(
        "SELECT * FROM listing_tracker WHERE tracking_id=?", (tracking_id,)
    ).fetchone()
