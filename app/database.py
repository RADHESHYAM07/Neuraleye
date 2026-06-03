"""
SQLite database layer with WAL mode, thread-safe connection pooling,
and graceful degradation for the Store Intelligence API.
"""

import sqlite3
import threading
import csv
import os
import logging
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timezone
from contextlib import contextmanager

logger = logging.getLogger("neuraleye.database")

# ---------------------------------------------------------------------------
# Database path resolution
# ---------------------------------------------------------------------------
_DB_DIR = os.environ.get("DB_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"))
_DB_PATH = os.path.join(_DB_DIR, "neuraleye.db")
_POS_CSV = os.environ.get(
    "POS_CSV_PATH",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "pos_transactions.csv"),
)

# ---------------------------------------------------------------------------
# Thread-local connection pool
# ---------------------------------------------------------------------------
_local = threading.local()
_init_lock = threading.Lock()
_initialized = False


def _get_conn() -> sqlite3.Connection:
    """Return a thread-local SQLite connection with WAL mode enabled."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
        conn = sqlite3.connect(_DB_PATH, timeout=30, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=10000")
        conn.row_factory = sqlite3.Row
        _local.conn = conn
    return conn


@contextmanager
def get_connection():
    """Context manager for database connections with error handling."""
    try:
        conn = _get_conn()
        yield conn
    except sqlite3.Error as exc:
        logger.error("Database error: %s", exc, exc_info=True)
        raise


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    store_id TEXT NOT NULL,
    camera_id TEXT NOT NULL,
    visitor_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    zone_id TEXT,
    dwell_ms INTEGER DEFAULT 0,
    is_staff INTEGER DEFAULT 0,
    confidence REAL DEFAULT 0.0,
    queue_depth INTEGER,
    sku_zone TEXT,
    session_seq INTEGER,
    ingested_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pos_transactions (
    store_id TEXT NOT NULL,
    transaction_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    basket_value REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_store ON events(store_id);
CREATE INDEX IF NOT EXISTS idx_events_store_type ON events(store_id, event_type);
CREATE INDEX IF NOT EXISTS idx_events_visitor ON events(visitor_id);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_pos_store ON pos_transactions(store_id);
CREATE INDEX IF NOT EXISTS idx_pos_timestamp ON pos_transactions(timestamp);
"""


def init_db() -> None:
    """Create tables/indexes and load POS seed data (idempotent)."""
    global _initialized
    with _init_lock:
        if _initialized:
            return
        try:
            conn = _get_conn()
            conn.executescript(_SCHEMA_SQL)
            conn.commit()
            logger.info("Database schema initialised at %s", _DB_PATH)
            _load_pos_csv(conn)
            _initialized = True
        except sqlite3.Error as exc:
            logger.error("Failed to initialise database: %s", exc, exc_info=True)
            raise


def _load_pos_csv(conn: sqlite3.Connection) -> None:
    """Load POS transactions from CSV if the table is empty."""
    try:
        row = conn.execute("SELECT COUNT(*) AS cnt FROM pos_transactions").fetchone()
        if row and row["cnt"] > 0:
            logger.info("POS transactions already loaded (%d rows)", row["cnt"])
            return
    except sqlite3.Error:
        pass

    if not os.path.isfile(_POS_CSV):
        logger.warning("POS CSV not found at %s – skipping seed", _POS_CSV)
        return

    inserted = 0
    try:
        with open(_POS_CSV, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            rows: list[tuple] = []
            for record in reader:
                rows.append((
                    record.get("store_id", ""),
                    record.get("transaction_id", ""),
                    record.get("timestamp", ""),
                    float(record.get("basket_value", 0)),
                ))
            conn.executemany(
                "INSERT OR IGNORE INTO pos_transactions (store_id, transaction_id, timestamp, basket_value) VALUES (?, ?, ?, ?)",
                rows,
            )
            conn.commit()
            inserted = len(rows)
        logger.info("Loaded %d POS transactions from CSV", inserted)
    except Exception as exc:
        logger.error("Error loading POS CSV: %s", exc, exc_info=True)


# ---------------------------------------------------------------------------
# Event helpers
# ---------------------------------------------------------------------------


def insert_event(event_dict: Dict[str, Any]) -> bool:
    """Insert a single event. Returns True if inserted, False if duplicate."""
    try:
        with get_connection() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO events
                   (event_id, store_id, camera_id, visitor_id, event_type,
                    timestamp, zone_id, dwell_ms, is_staff, confidence,
                    queue_depth, sku_zone, session_seq, ingested_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event_dict["event_id"],
                    event_dict["store_id"],
                    event_dict["camera_id"],
                    event_dict["visitor_id"],
                    event_dict["event_type"],
                    event_dict["timestamp"],
                    event_dict.get("zone_id"),
                    event_dict.get("dwell_ms", 0),
                    1 if event_dict.get("is_staff") else 0,
                    event_dict.get("confidence", 0.0),
                    event_dict.get("queue_depth"),
                    event_dict.get("sku_zone"),
                    event_dict.get("session_seq"),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
            return conn.total_changes > 0
    except sqlite3.Error as exc:
        logger.error("insert_event failed: %s", exc)
        return False


def insert_events_bulk(event_dicts: List[Dict[str, Any]]) -> int:
    """Bulk insert events. Returns the number of newly inserted rows."""
    if not event_dicts:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for e in event_dicts:
        rows.append((
            e["event_id"],
            e["store_id"],
            e["camera_id"],
            e["visitor_id"],
            e["event_type"],
            e["timestamp"],
            e.get("zone_id"),
            e.get("dwell_ms", 0),
            1 if e.get("is_staff") else 0,
            e.get("confidence", 0.0),
            e.get("queue_depth"),
            e.get("sku_zone"),
            e.get("session_seq"),
            now,
        ))
    try:
        with get_connection() as conn:
            before = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            conn.executemany(
                """INSERT OR IGNORE INTO events
                   (event_id, store_id, camera_id, visitor_id, event_type,
                    timestamp, zone_id, dwell_ms, is_staff, confidence,
                    queue_depth, sku_zone, session_seq, ingested_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
            conn.commit()
            after = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            return after - before
    except sqlite3.Error as exc:
        logger.error("insert_events_bulk failed: %s", exc)
        return 0


def get_events_by_store(
    store_id: str,
    event_types: Optional[List[str]] = None,
    start_ts: Optional[str] = None,
    end_ts: Optional[str] = None,
    exclude_staff: bool = True,
) -> List[Dict[str, Any]]:
    """Retrieve events for a store with optional filters."""
    try:
        with get_connection() as conn:
            sql = "SELECT * FROM events WHERE store_id = ?"
            params: list = [store_id]

            if exclude_staff:
                sql += " AND is_staff = 0"
            if event_types:
                placeholders = ",".join("?" for _ in event_types)
                sql += f" AND event_type IN ({placeholders})"
                params.extend(event_types)
            if start_ts:
                sql += " AND timestamp >= ?"
                params.append(start_ts)
            if end_ts:
                sql += " AND timestamp <= ?"
                params.append(end_ts)

            sql += " ORDER BY timestamp ASC"
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        logger.error("get_events_by_store failed: %s", exc)
        return []


def get_pos_transactions(
    store_id: str,
    start_ts: Optional[str] = None,
    end_ts: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Retrieve POS transactions for a store."""
    try:
        with get_connection() as conn:
            sql = "SELECT * FROM pos_transactions WHERE store_id = ?"
            params: list = [store_id]
            if start_ts:
                sql += " AND timestamp >= ?"
                params.append(start_ts)
            if end_ts:
                sql += " AND timestamp <= ?"
                params.append(end_ts)
            sql += " ORDER BY timestamp ASC"
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        logger.error("get_pos_transactions failed: %s", exc)
        return []


def get_all_store_ids() -> List[str]:
    """Return distinct store_ids from events table."""
    try:
        with get_connection() as conn:
            rows = conn.execute("SELECT DISTINCT store_id FROM events").fetchall()
            return [r["store_id"] for r in rows]
    except sqlite3.Error as exc:
        logger.error("get_all_store_ids failed: %s", exc)
        return []


def get_last_event_per_store() -> Dict[str, str]:
    """Return {store_id: last_event_timestamp} mapping."""
    try:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT store_id, MAX(timestamp) AS last_ts FROM events GROUP BY store_id"
            ).fetchall()
            return {r["store_id"]: r["last_ts"] for r in rows}
    except sqlite3.Error as exc:
        logger.error("get_last_event_per_store failed: %s", exc)
        return {}


def query_raw(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    """Execute arbitrary read-only SQL and return results as dicts."""
    try:
        with get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        logger.error("query_raw failed: %s", exc)
        return []
