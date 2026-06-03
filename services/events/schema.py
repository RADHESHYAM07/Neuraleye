"""
NeuralEye — Shared Event Schema v1.2
All services import from this module for type safety and consistency.
"""
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
import uuid


class EventType(str, Enum):
    PERSON_ENTERED    = "PERSON_ENTERED"
    PERSON_LEFT       = "PERSON_LEFT"
    ZONE_ENTERED      = "ZONE_ENTERED"
    ZONE_EXITED       = "ZONE_EXITED"
    DWELL_START       = "DWELL_START"
    DWELL_END         = "DWELL_END"
    DWELL_ANOMALY     = "DWELL_ANOMALY"
    QUEUE_ALERT       = "QUEUE_ALERT"
    CROWD_SPIKE       = "CROWD_SPIKE"
    LOITERING         = "LOITERING"
    FRAME_STATS       = "FRAME_STATS"


class BoundingBox(BaseModel):
    x: float; y: float; w: float; h: float


class TrackSource(BaseModel):
    camera_id: str
    store_id: str
    frame_id: Optional[int] = None


class NeuralEvent(BaseModel):
    schema_version: str = "1.2"
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: EventType
    timestamp_utc: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    track_id: Optional[int] = None
    zone_id: Optional[str] = None
    source: TrackSource
    payload: Dict[str, Any] = {}

    def to_redis(self) -> Dict[str, str]:
        """Flat dict for Redis Streams XADD"""
        import json
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp_utc": self.timestamp_utc,
            "track_id": str(self.track_id or ""),
            "zone_id": self.zone_id or "",
            "camera_id": self.source.camera_id,
            "store_id": self.source.store_id,
            "payload": json.dumps(self.payload),
        }

    @classmethod
    def from_redis(cls, data: Dict[str, str]) -> "NeuralEvent":
        import json
        return cls(
            schema_version=data.get("schema_version", "1.2"),
            event_id=data["event_id"],
            event_type=EventType(data["event_type"]),
            timestamp_utc=data["timestamp_utc"],
            track_id=int(data["track_id"]) if data.get("track_id") else None,
            zone_id=data.get("zone_id") or None,
            source=TrackSource(
                camera_id=data["camera_id"],
                store_id=data["store_id"],
            ),
            payload=json.loads(data.get("payload", "{}")),
        )


# Redis stream key
EVENTS_STREAM = "neuraleye:events"
CONSUMER_GROUP = "analytics-group"
