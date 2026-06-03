from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime
import uuid


class EventType(str, Enum):
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    ZONE_ENTER = "ZONE_ENTER"
    ZONE_EXIT = "ZONE_EXIT"
    ZONE_DWELL = "ZONE_DWELL"
    BILLING_QUEUE_JOIN = "BILLING_QUEUE_JOIN"
    BILLING_QUEUE_ABANDON = "BILLING_QUEUE_ABANDON"
    REENTRY = "REENTRY"


class EventMetadata(BaseModel):
    queue_depth: Optional[int] = None
    sku_zone: Optional[str] = None
    session_seq: Optional[int] = None


class StoreEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    store_id: str
    camera_id: str
    visitor_id: str
    event_type: EventType
    timestamp: str  # ISO-8601 UTC
    zone_id: Optional[str] = None
    dwell_ms: int = 0
    is_staff: bool = False
    confidence: float = 0.0
    metadata: EventMetadata = Field(default_factory=EventMetadata)


class IngestRequest(BaseModel):
    events: List[StoreEvent] = Field(..., max_length=500)


class IngestResponse(BaseModel):
    accepted: int
    rejected: int
    errors: List[Dict[str, Any]] = []


class MetricsResponse(BaseModel):
    store_id: str
    period: str
    unique_visitors: int
    conversion_rate: float
    avg_dwell_by_zone: Dict[str, float]
    current_queue_depth: int
    abandonment_rate: float


class FunnelStage(BaseModel):
    stage: str
    visitors: int
    drop_off_pct: float


class FunnelResponse(BaseModel):
    store_id: str
    period: str
    stages: List[FunnelStage]


class HeatmapZone(BaseModel):
    zone_id: str
    visit_count: int
    avg_dwell_ms: float
    intensity: int  # normalized 0-100
    data_confidence: Optional[str] = None  # 'LOW' if <20 sessions


class HeatmapResponse(BaseModel):
    store_id: str
    period: str
    zones: List[HeatmapZone]


class AnomalyItem(BaseModel):
    anomaly_id: str
    type: str
    severity: str  # INFO, WARN, CRITICAL
    detected_at: str
    details: Dict[str, Any]
    suggested_action: str


class AnomaliesResponse(BaseModel):
    store_id: str
    active_anomalies: List[AnomalyItem]


class StoreHealth(BaseModel):
    store_id: str
    last_event_at: Optional[str] = None
    status: str  # OK, STALE_FEED


class HealthResponse(BaseModel):
    status: str
    version: str
    uptime_seconds: float
    stores: List[StoreHealth]
