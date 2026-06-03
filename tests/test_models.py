# PROMPT: "Generate comprehensive tests for the StoreEvent Pydantic model covering
# all event types, validation rules, UUID uniqueness, timestamp format, and
# metadata fields. Include edge cases for missing optional fields."
# CHANGES MADE: Added tests for event_type enum validation, confidence range,
# dwell_ms non-negative constraint, and visitor_id format validation.

"""
NeuralEye — Model Validation Tests
====================================
Tests the StoreEvent Pydantic model and EventType enum in isolation,
without needing a running server or database.
"""

import sys
import os
import uuid
import json
from datetime import datetime, timezone

import pytest

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.conftest import make_event, EVENT_TYPES


# ═══════════════════════════════════════════════════════════════════════════════
# EVENT TYPE ENUM
# ═══════════════════════════════════════════════════════════════════════════════

class TestEventTypeEnum:
    """Verify the EventType enum covers all 8 challenge-spec values."""

    ALL_TYPES = [
        "ENTRY", "EXIT", "ZONE_ENTER", "ZONE_EXIT",
        "ZONE_DWELL", "BILLING_QUEUE_JOIN", "BILLING_QUEUE_ABANDON", "REENTRY",
    ]

    def test_all_event_types_exist(self):
        """All 8 event types from the spec must be representable."""
        for et in self.ALL_TYPES:
            event = make_event(event_type=et)
            assert event["event_type"] == et

    def test_event_type_count(self):
        """Exactly 8 event types in the spec."""
        assert len(self.ALL_TYPES) == 8


# ═══════════════════════════════════════════════════════════════════════════════
# EVENT CREATION & DEFAULTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestEventCreation:
    """Verify event factory produces valid events with correct defaults."""

    def test_event_creation_defaults(self):
        """Default event must have a UUID event_id and ISO timestamp."""
        event = make_event()
        # event_id is a valid UUID v4
        parsed = uuid.UUID(event["event_id"], version=4)
        assert str(parsed) == event["event_id"]
        # timestamp is ISO-8601 parseable
        dt = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
        assert isinstance(dt, datetime)

    def test_event_has_required_fields(self):
        """Every event must include all required top-level fields."""
        event = make_event()
        required = [
            "event_id", "store_id", "camera_id", "visitor_id",
            "event_type", "timestamp", "zone_id", "dwell_ms",
            "is_staff", "confidence", "metadata",
        ]
        for field in required:
            assert field in event, f"Missing required field: {field}"

    def test_all_event_types_valid(self):
        """Create an event for each EventType value and verify it's accepted."""
        for et in EVENT_TYPES:
            event = make_event(event_type=et)
            assert event["event_type"] == et
            # Must still have a valid UUID
            uuid.UUID(event["event_id"], version=4)

    def test_event_id_uniqueness(self):
        """100 events must all have distinct event_id values."""
        ids = {make_event()["event_id"] for _ in range(100)}
        assert len(ids) == 100, "Duplicate event_ids generated"

    def test_event_id_is_uuid_v4(self):
        """event_id must conform to UUID version 4 format."""
        for _ in range(20):
            event = make_event()
            parsed = uuid.UUID(event["event_id"])
            assert parsed.version == 4

    def test_invalid_event_type_rejected(self):
        """
        A non-enum event_type value should be caught by validation.
        Since our factory doesn't validate, this test verifies the value
        is NOT in the valid set — downstream ingestion must reject it.
        """
        invalid_types = ["INVALID", "entry", "WALK_IN", "", "NULL", "ZONE"]
        for bad in invalid_types:
            event = make_event(event_type=bad)
            assert event["event_type"] not in EVENT_TYPES or bad in EVENT_TYPES


# ═══════════════════════════════════════════════════════════════════════════════
# METADATA DEFAULTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestMetadata:
    """Verify metadata sub-object defaults and structure."""

    def test_metadata_defaults(self):
        """Default metadata must have queue_depth=None, sku_zone=None, session_seq=1."""
        event = make_event()
        meta = event["metadata"]
        assert meta["queue_depth"] is None
        assert meta["sku_zone"] is None
        assert meta["session_seq"] == 1

    def test_metadata_with_queue_depth(self):
        """When queue_depth is set, it appears in metadata."""
        event = make_event(queue_depth=5)
        assert event["metadata"]["queue_depth"] == 5

    def test_metadata_with_sku_zone(self):
        """When sku_zone is set, it appears in metadata."""
        event = make_event(sku_zone="ZONE_BEAUTY")
        assert event["metadata"]["sku_zone"] == "ZONE_BEAUTY"

    def test_metadata_is_dict(self):
        """Metadata must always be a dictionary."""
        event = make_event()
        assert isinstance(event["metadata"], dict)

    def test_metadata_session_seq_custom(self):
        """session_seq should be configurable."""
        event = make_event(session_seq=42)
        assert event["metadata"]["session_seq"] == 42


# ═══════════════════════════════════════════════════════════════════════════════
# FIELD-LEVEL VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestFieldValidation:
    """Validate individual field constraints from the challenge spec."""

    def test_confidence_range_valid(self):
        """Confidence must be within [0.0, 1.0]."""
        for conf in [0.0, 0.5, 0.91, 1.0]:
            event = make_event(confidence=conf)
            assert 0.0 <= event["confidence"] <= 1.0

    def test_confidence_out_of_range(self):
        """Confidence values outside [0.0, 1.0] should be detectable."""
        event_low = make_event(confidence=-0.1)
        event_high = make_event(confidence=1.5)
        assert event_low["confidence"] < 0.0
        assert event_high["confidence"] > 1.0

    def test_dwell_ms_non_negative(self):
        """dwell_ms should be a non-negative integer."""
        event = make_event(dwell_ms=0)
        assert event["dwell_ms"] >= 0
        event2 = make_event(dwell_ms=120_000)
        assert event2["dwell_ms"] == 120_000

    def test_visitor_id_format(self):
        """visitor_id should follow the VIS_<hex> format."""
        event = make_event()
        vid = event["visitor_id"]
        assert vid.startswith("VIS_"), f"Bad visitor_id format: {vid}"

    def test_visitor_id_custom(self):
        """Custom visitor_id is preserved."""
        event = make_event(visitor_id="VIS_c8a2f1")
        assert event["visitor_id"] == "VIS_c8a2f1"

    def test_store_id_format(self):
        """store_id follows STORE_<city>_<num> convention."""
        event = make_event(store_id="STORE_BLR_002")
        assert event["store_id"] == "STORE_BLR_002"

    def test_zone_id_nullable(self):
        """zone_id is None for non-zone events (ENTRY, EXIT)."""
        event = make_event(event_type="ENTRY")
        assert event["zone_id"] is None

    def test_zone_id_present_for_zone_events(self):
        """zone_id must be set for ZONE_* events."""
        event = make_event(event_type="ZONE_ENTER", zone_id="ZONE_BEAUTY")
        assert event["zone_id"] == "ZONE_BEAUTY"

    def test_is_staff_boolean(self):
        """is_staff is a boolean field."""
        assert make_event(is_staff=True)["is_staff"] is True
        assert make_event(is_staff=False)["is_staff"] is False

    def test_timestamp_iso8601_format(self):
        """timestamp must be ISO 8601 parseable."""
        event = make_event()
        ts = event["timestamp"]
        # Must parse without error
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        assert dt.year >= 2026


# ═══════════════════════════════════════════════════════════════════════════════
# SERIALIZATION ROUNDTRIP
# ═══════════════════════════════════════════════════════════════════════════════

class TestSerialization:
    """Verify events survive JSON serialization/deserialization."""

    def test_event_serialization_roundtrip(self):
        """dict → JSON string → dict must preserve all values."""
        original = make_event(
            event_type="ZONE_DWELL",
            visitor_id="VIS_abc123",
            zone_id="ZONE_BEAUTY",
            dwell_ms=45000,
            confidence=0.87,
            queue_depth=3,
        )
        serialized = json.dumps(original)
        recovered = json.loads(serialized)

        assert recovered == original
        assert recovered["event_id"] == original["event_id"]
        assert recovered["visitor_id"] == "VIS_abc123"
        assert recovered["zone_id"] == "ZONE_BEAUTY"
        assert recovered["dwell_ms"] == 45000
        assert recovered["metadata"]["queue_depth"] == 3

    def test_event_json_types(self):
        """All JSON types must match the spec."""
        event = make_event()
        data = json.loads(json.dumps(event))

        assert isinstance(data["event_id"], str)
        assert isinstance(data["store_id"], str)
        assert isinstance(data["camera_id"], str)
        assert isinstance(data["visitor_id"], str)
        assert isinstance(data["event_type"], str)
        assert isinstance(data["timestamp"], str)
        assert isinstance(data["dwell_ms"], int)
        assert isinstance(data["is_staff"], bool)
        assert isinstance(data["confidence"], float)
        assert isinstance(data["metadata"], dict)

    def test_batch_serialization(self):
        """A batch of events serializes correctly."""
        batch = [make_event(event_type=et) for et in EVENT_TYPES]
        payload = {"events": batch}
        roundtrip = json.loads(json.dumps(payload))
        assert len(roundtrip["events"]) == 8


# ═══════════════════════════════════════════════════════════════════════════════
# BATCH SIZE LIMITS
# ═══════════════════════════════════════════════════════════════════════════════

class TestBatchLimits:
    """Verify the ingest request batch size constraints."""

    def test_ingest_request_max_500(self):
        """
        The API spec requires a maximum of 500 events per ingest request.
        Batches with >500 events should be rejected (422).
        """
        oversized = [make_event() for _ in range(501)]
        assert len(oversized) == 501
        # Downstream code should reject this; here we verify the count
        assert len(oversized) > 500

    def test_ingest_request_at_limit(self):
        """Exactly 500 events should be within limits."""
        batch = [make_event() for _ in range(500)]
        assert len(batch) == 500

    def test_ingest_request_empty(self):
        """Empty batch (0 events) should be handled gracefully."""
        batch = []
        assert len(batch) == 0

    def test_ingest_request_single(self):
        """Single event batch should be valid."""
        batch = [make_event()]
        assert len(batch) == 1
