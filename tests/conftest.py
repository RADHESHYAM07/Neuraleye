# PROMPT: "Generate shared pytest fixtures for the NeuralEye Store Intelligence
# API test suite. Include sample event factory, batch event generator, FastAPI
# TestClient, clean database fixture, and populated database fixture."
# CHANGES MADE: Added full session flow generator in sample_events_batch, temp
# file DB for isolation, and populated_db with realistic multi-visitor data
# covering all 8 event types including REENTRY and staff visitors.

"""
NeuralEye — Shared Test Fixtures
================================
Centralised fixtures used across all test modules. Every test gets a fresh
SQLite database (via tmp_path) so tests never leak state to each other.
"""

import os
import sys
import uuid
import tempfile
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Generator

import pytest

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path so `from app.main import app` works
# regardless of the directory pytest is invoked from.
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# We import lazily inside fixtures so that collection never fails if the
# application code has not been installed yet (e.g. during a lint-only CI run).


# ── Constants ────────────────────────────────────────────────────────────────

STORE_ID = "STORE_BLR_002"
CAMERA_ID = "CAM_ENTRY_01"
ZONE_IDS = ["ZONE_BEAUTY", "ZONE_SKINCARE", "ZONE_HAIRCARE", "ZONE_CHECKOUT"]

EVENT_TYPES = [
    "ENTRY", "EXIT", "ZONE_ENTER", "ZONE_EXIT",
    "ZONE_DWELL", "BILLING_QUEUE_JOIN", "BILLING_QUEUE_ABANDON", "REENTRY",
]

# ── SQLite schema that the API expects ───────────────────────────────────────

DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id    TEXT PRIMARY KEY,
    store_id    TEXT NOT NULL,
    camera_id   TEXT NOT NULL,
    visitor_id  TEXT NOT NULL,
    event_type  TEXT NOT NULL,
    timestamp   TEXT NOT NULL,
    zone_id     TEXT,
    dwell_ms    INTEGER DEFAULT 0,
    is_staff    INTEGER DEFAULT 0,
    confidence  REAL DEFAULT 0.90,
    metadata    TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_events_store ON events(store_id);
CREATE INDEX IF NOT EXISTS idx_events_visitor ON events(visitor_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(timestamp);

CREATE TABLE IF NOT EXISTS pos_transactions (
    txn_id      TEXT PRIMARY KEY,
    store_id    TEXT NOT NULL,
    timestamp   TEXT NOT NULL,
    amount      REAL,
    items       INTEGER
);
"""


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLE-EVENT FACTORY
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def sample_event() -> dict:
    """Return a single valid StoreEvent dict matching the challenge spec."""
    return _make_event()


def _make_event(
    event_type: str = "ENTRY",
    visitor_id: str | None = None,
    store_id: str = STORE_ID,
    camera_id: str = CAMERA_ID,
    zone_id: str | None = None,
    dwell_ms: int = 0,
    is_staff: bool = False,
    confidence: float = 0.91,
    timestamp: str | None = None,
    session_seq: int = 1,
    queue_depth: int | None = None,
    sku_zone: str | None = None,
) -> dict:
    """Internal helper — builds a spec-compliant event dict."""
    return {
        "event_id": str(uuid.uuid4()),
        "store_id": store_id,
        "camera_id": camera_id,
        "visitor_id": visitor_id or f"VIS_{uuid.uuid4().hex[:6]}",
        "event_type": event_type,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "zone_id": zone_id,
        "dwell_ms": dwell_ms,
        "is_staff": is_staff,
        "confidence": confidence,
        "metadata": {
            "queue_depth": queue_depth,
            "sku_zone": sku_zone,
            "session_seq": session_seq,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# BATCH EVENT FACTORY — 10 visitors, full session flows
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def sample_events_batch() -> list[dict]:
    """
    Return 10 visitors' worth of events covering a realistic session flow:

    Visitor journey:
        ENTRY → ZONE_ENTER(beauty) → ZONE_DWELL(beauty) → ZONE_EXIT(beauty)
        → ZONE_ENTER(checkout) → BILLING_QUEUE_JOIN → EXIT

    Some visitors also have REENTRY, BILLING_QUEUE_ABANDON, and staff flags
    to exercise edge-case handling.
    """
    events: list[dict] = []
    base_time = datetime(2026, 3, 3, 14, 0, 0, tzinfo=timezone.utc)

    for i in range(10):
        vid = f"VIS_{uuid.uuid4().hex[:6]}"
        t = base_time + timedelta(minutes=i * 3)
        is_staff = (i == 9)  # last visitor is staff

        # 1. ENTRY
        events.append(_make_event(
            event_type="ENTRY", visitor_id=vid, timestamp=t.isoformat(),
            is_staff=is_staff, session_seq=1,
        ))

        # 2. ZONE_ENTER beauty
        t += timedelta(seconds=30)
        events.append(_make_event(
            event_type="ZONE_ENTER", visitor_id=vid,
            zone_id="ZONE_BEAUTY", timestamp=t.isoformat(),
            is_staff=is_staff, session_seq=2,
        ))

        # 3. ZONE_DWELL beauty
        t += timedelta(seconds=120)
        events.append(_make_event(
            event_type="ZONE_DWELL", visitor_id=vid,
            zone_id="ZONE_BEAUTY", dwell_ms=120_000,
            timestamp=t.isoformat(), is_staff=is_staff, session_seq=3,
        ))

        # 4. ZONE_EXIT beauty
        t += timedelta(seconds=5)
        events.append(_make_event(
            event_type="ZONE_EXIT", visitor_id=vid,
            zone_id="ZONE_BEAUTY", timestamp=t.isoformat(),
            is_staff=is_staff, session_seq=4,
        ))

        # 5. ZONE_ENTER checkout (only first 7 visitors)
        if i < 7:
            t += timedelta(seconds=60)
            events.append(_make_event(
                event_type="ZONE_ENTER", visitor_id=vid,
                zone_id="ZONE_CHECKOUT", timestamp=t.isoformat(),
                is_staff=is_staff, session_seq=5,
            ))

            # 6. BILLING_QUEUE_JOIN (only first 5)
            if i < 5:
                t += timedelta(seconds=10)
                events.append(_make_event(
                    event_type="BILLING_QUEUE_JOIN", visitor_id=vid,
                    zone_id="ZONE_CHECKOUT", timestamp=t.isoformat(),
                    queue_depth=i + 1, is_staff=is_staff, session_seq=6,
                ))

                # 7. One visitor abandons the queue
                if i == 4:
                    t += timedelta(seconds=45)
                    events.append(_make_event(
                        event_type="BILLING_QUEUE_ABANDON", visitor_id=vid,
                        zone_id="ZONE_CHECKOUT", timestamp=t.isoformat(),
                        queue_depth=i, is_staff=is_staff, session_seq=7,
                    ))

        # 8. REENTRY for visitor 2
        if i == 2:
            t += timedelta(minutes=10)
            events.append(_make_event(
                event_type="REENTRY", visitor_id=vid,
                timestamp=t.isoformat(), session_seq=8,
            ))

        # 9. EXIT
        t += timedelta(seconds=90)
        events.append(_make_event(
            event_type="EXIT", visitor_id=vid, timestamp=t.isoformat(),
            is_staff=is_staff, session_seq=99,
        ))

    return events


# ═══════════════════════════════════════════════════════════════════════════════
# FASTAPI TEST CLIENT
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def client(tmp_path):
    """
    Yield a FastAPI TestClient wired to a fresh temp database.

    The DB_PATH env-var is set *before* the app module is imported so the
    application picks up the temporary path instead of the production DB.
    """
    db_file = str(tmp_path / "test_neuraleye.db")
    os.environ["DB_PATH"] = db_file

    # Initialise schema
    conn = sqlite3.connect(db_file)
    conn.executescript(DB_SCHEMA)
    conn.commit()
    conn.close()

    from app.main import app  # noqa: late import
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


# ═══════════════════════════════════════════════════════════════════════════════
# CLEAN DATABASE (empty, schema only)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def clean_db(tmp_path) -> Generator[sqlite3.Connection, None, None]:
    """
    Create a fresh SQLite database with the application schema.
    Yields the open connection; tears it down after the test.
    """
    db_file = str(tmp_path / "clean_neuraleye.db")
    os.environ["DB_PATH"] = db_file

    conn = sqlite3.connect(db_file)
    conn.executescript(DB_SCHEMA)
    conn.commit()
    yield conn
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# POPULATED DATABASE (pre-loaded events for metric testing)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def populated_db(tmp_path, sample_events_batch) -> Generator[sqlite3.Connection, None, None]:
    """
    Create a database pre-loaded with the sample_events_batch fixture data.
    Useful for testing metric endpoints without needing to POST first.
    """
    db_file = str(tmp_path / "populated_neuraleye.db")
    os.environ["DB_PATH"] = db_file

    conn = sqlite3.connect(db_file)
    conn.executescript(DB_SCHEMA)

    for ev in sample_events_batch:
        meta_json = ev.get("metadata", {})
        if isinstance(meta_json, dict):
            import json
            meta_json = json.dumps(meta_json)
        conn.execute(
            "INSERT OR IGNORE INTO events "
            "(event_id, store_id, camera_id, visitor_id, event_type, "
            " timestamp, zone_id, dwell_ms, is_staff, confidence, metadata) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                ev["event_id"], ev["store_id"], ev["camera_id"],
                ev["visitor_id"], ev["event_type"], ev["timestamp"],
                ev.get("zone_id"), ev.get("dwell_ms", 0),
                int(ev.get("is_staff", False)),
                ev.get("confidence", 0.90), meta_json,
            ),
        )
    conn.commit()
    yield conn
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER — exposed for other test modules to import
# ═══════════════════════════════════════════════════════════════════════════════

def make_event(**kwargs) -> dict:
    """Public wrapper around the event factory for use in individual tests."""
    return _make_event(**kwargs)


def make_events_for_visitor(
    visitor_id: str,
    zones: list[str],
    *,
    store_id: str = STORE_ID,
    is_staff: bool = False,
    include_billing: bool = False,
    include_reentry: bool = False,
) -> list[dict]:
    """
    Build a full session flow for a single visitor through the given zones.
    Returns a list of ordered events.
    """
    events: list[dict] = []
    t = datetime.now(timezone.utc)
    seq = 1

    events.append(_make_event(
        event_type="ENTRY", visitor_id=visitor_id, store_id=store_id,
        timestamp=t.isoformat(), is_staff=is_staff, session_seq=seq,
    ))
    seq += 1

    for zone in zones:
        t += timedelta(seconds=30)
        events.append(_make_event(
            event_type="ZONE_ENTER", visitor_id=visitor_id,
            zone_id=zone, store_id=store_id, timestamp=t.isoformat(),
            is_staff=is_staff, session_seq=seq,
        ))
        seq += 1

        t += timedelta(seconds=90)
        events.append(_make_event(
            event_type="ZONE_DWELL", visitor_id=visitor_id,
            zone_id=zone, dwell_ms=90_000, store_id=store_id,
            timestamp=t.isoformat(), is_staff=is_staff, session_seq=seq,
        ))
        seq += 1

        t += timedelta(seconds=5)
        events.append(_make_event(
            event_type="ZONE_EXIT", visitor_id=visitor_id,
            zone_id=zone, store_id=store_id, timestamp=t.isoformat(),
            is_staff=is_staff, session_seq=seq,
        ))
        seq += 1

    if include_billing:
        t += timedelta(seconds=15)
        events.append(_make_event(
            event_type="BILLING_QUEUE_JOIN", visitor_id=visitor_id,
            zone_id="ZONE_CHECKOUT", store_id=store_id,
            timestamp=t.isoformat(), queue_depth=2,
            is_staff=is_staff, session_seq=seq,
        ))
        seq += 1

    if include_reentry:
        t += timedelta(minutes=10)
        events.append(_make_event(
            event_type="REENTRY", visitor_id=visitor_id,
            store_id=store_id, timestamp=t.isoformat(),
            is_staff=is_staff, session_seq=seq,
        ))
        seq += 1

    t += timedelta(seconds=60)
    events.append(_make_event(
        event_type="EXIT", visitor_id=visitor_id, store_id=store_id,
        timestamp=t.isoformat(), is_staff=is_staff, session_seq=seq,
    ))

    return events
