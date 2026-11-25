-- The same record dashboard/server.py keeps, plus the index that lets the
-- Worker's window queries reach untimed rows without scanning the table.
-- Apply with:
--   npx wrangler d1 execute crynet --remote --file worker/schema.sql

CREATE TABLE IF NOT EXISTS devices (
    device     TEXT PRIMARY KEY,
    name       TEXT,
    fw         TEXT,
    first_seen INTEGER,
    last_seen  INTEGER
);

CREATE TABLE IF NOT EXISTS events (
    device      TEXT NOT NULL,
    seq         INTEGER NOT NULL,
    kind        TEXT NOT NULL,
    cot         INTEGER,
    start_at    INTEGER,   -- epoch seconds, 0 = the hub did not know the time
    end_at      INTEGER,
    duration_s  INTEGER,
    peak_conf   INTEGER,
    windows     INTEGER,
    peak_rms    REAL,
    mean_rms    REAL,
    boot        INTEGER,
    uptime_ms   INTEGER,
    received_at INTEGER,
    PRIMARY KEY (device, seq)
);

CREATE INDEX IF NOT EXISTS idx_events_start    ON events (start_at);
CREATE INDEX IF NOT EXISTS idx_events_kind     ON events (kind);
CREATE INDEX IF NOT EXISTS idx_events_received ON events (received_at);

-- Who is here.  The cots have no network of their own -- they talk to
-- the hub over its radio -- so the hub is the only thing that can answer
-- for them, and it does so once a minute whether or not there is a cry
-- to record.  One row per cot, replaced each time the hub speaks.
CREATE TABLE IF NOT EXISTS presence (
    device  TEXT NOT NULL,
    cot     INTEGER NOT NULL,
    online  INTEGER NOT NULL,
    deaf    INTEGER NOT NULL DEFAULT 0,
    rssi    INTEGER,
    at      INTEGER,
    PRIMARY KEY (device, cot)
);
