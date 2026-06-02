from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, model_validator, field_validator, ConfigDict
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

class EventMeta(BaseModel):
    model_config = ConfigDict(extra="allow")
    queue_depth: Optional[int] = Field(None, description="Current queue depth if in billing zone")
    sku_zone: Optional[str] = Field(None, description="Product category or brand of the zone")
    session_seq: Optional[int] = Field(None, description="Sequence number of the session")

    @model_validator(mode="after")
    def validate_metadata(self) -> 'EventMeta':
        # Custom metadata validation if needed
        return self

class Event(BaseModel):
    event_id: str = Field(..., description="UUID v4, globally unique")
    store_id: str = Field(..., description="Store Identifier")
    camera_id: str = Field(..., description="Camera identifier")
    visitor_id: str = Field(..., description="Unique Visitor identifier")
    event_type: EventType = Field(..., description="Type of event")
    timestamp: datetime = Field(..., description="ISO-8601 UTC timestamp")
    zone_id: Optional[str] = Field(None, description="Zone identifier, null for ENTRY/EXIT")
    dwell_ms: Optional[int] = Field(None, description="Duration in ms for dwell events")
    is_staff: bool = Field(False, description="Exclusion flag for store employees")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Model/Deduplication confidence")
    metadata: EventMeta = Field(default_factory=EventMeta, description="Additional event metadata")

    @field_validator("event_id")
    @classmethod
    def validate_uuid(cls, v: str) -> str:
        try:
            uuid.UUID(v)
        except ValueError:
            raise ValueError("event_id must be a valid UUID v4")
        return v

    @model_validator(mode="after")
    def validate_event(self) -> 'Event':
        if self.event_type in (EventType.ENTRY, EventType.EXIT, EventType.REENTRY):
            if self.zone_id is not None:
                raise ValueError(f"zone_id must be null for event type {self.event_type.value}")
        else:
            if self.zone_id is None:
                raise ValueError(f"zone_id cannot be null for event type {self.event_type.value}")

        if self.event_type == EventType.ZONE_DWELL:
            if self.dwell_ms is None:
                raise ValueError("dwell_ms cannot be null for ZONE_DWELL event")
            if self.dwell_ms < 0:
                raise ValueError("dwell_ms must be non-negative")
        return self

class IngestRequest(BaseModel):
    events: List[Any] = Field(..., max_length=500)

class IngestErrorDetail(BaseModel):
    event_id: Optional[str] = None
    reason: str

class IngestResponse(BaseModel):
    accepted: int
    rejected: int
    errors: List[IngestErrorDetail]

class ZoneMetric(BaseModel):
    zone_id: str
    avg_dwell_ms: float

class MetricsResponse(BaseModel):
    store_id: str
    unique_visitors: int
    conversion_rate: float
    avg_dwell_by_zone: Dict[str, float]
    current_queue_depth: int
    abandonment_rate: float
    data_window: Dict[str, str]

class FunnelStage(BaseModel):
    name: str
    count: int
    drop_off_pct: float

class FunnelResponse(BaseModel):
    store_id: str
    stages: List[FunnelStage]

class HeatmapZone(BaseModel):
    zone_id: str
    visit_count: int
    avg_dwell_ms: float
    normalized_score: int
    data_confidence: str

class HeatmapResponse(BaseModel):
    store_id: str
    zones: List[HeatmapZone]

class Anomaly(BaseModel):
    type: str
    severity: str
    details: str
    detected_at: datetime
    suggested_action: str

class AnomalyResponse(BaseModel):
    store_id: str
    anomalies: List[Anomaly]

class StoreHealth(BaseModel):
    last_event_at: Optional[datetime] = None
    feed_status: str
    event_count: int

class HealthResponse(BaseModel):
    status: str
    stores: Dict[str, StoreHealth]
    uptime_seconds: float
    version: str
