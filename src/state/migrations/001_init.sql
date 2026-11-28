-- src/state/migrations/001_init.sql
CREATE TABLE listings (
    fingerprint  TEXT PRIMARY KEY,
    first_seen   INTEGER NOT NULL,
    last_seen    INTEGER NOT NULL,
    sources      TEXT NOT NULL,
    canonical    TEXT NOT NULL,
    alerted_at   INTEGER,
    msg_id       INTEGER
);
CREATE INDEX idx_listings_last_seen ON listings(last_seen);

CREATE TABLE tracker (
    tracking_id  TEXT PRIMARY KEY,
    fingerprint  TEXT NOT NULL REFERENCES listings(fingerprint),
    status       TEXT NOT NULL,
    updated_at   INTEGER NOT NULL
);

CREATE TABLE runs (
    run_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at    INTEGER NOT NULL,
    duration_ms   INTEGER NOT NULL,
    raw_count     INTEGER NOT NULL,
    after_filter  INTEGER NOT NULL,
    after_dedup   INTEGER NOT NULL,
    alerted       INTEGER NOT NULL,
    per_source    TEXT NOT NULL,
    breaker_open  TEXT NOT NULL
);

CREATE TABLE travel_cache (
    cache_key   TEXT PRIMARY KEY,
    minutes     REAL NOT NULL,
    source      TEXT NOT NULL,
    cached_at   INTEGER NOT NULL
);

CREATE TABLE pending_alerts (
    pending_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint   TEXT NOT NULL REFERENCES listings(fingerprint),
    queued_at     INTEGER NOT NULL,
    retry_count   INTEGER NOT NULL DEFAULT 0,
    last_error    TEXT
);
CREATE INDEX idx_pending_queued ON pending_alerts(queued_at);

CREATE TABLE schema_version (version INTEGER PRIMARY KEY);
INSERT INTO schema_version (version) VALUES (1);
