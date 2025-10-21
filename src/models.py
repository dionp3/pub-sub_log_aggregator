# src/models.py
from pydantic import BaseModel, Field
import datetime
from typing import List, Optional

class EventPayload(BaseModel):
    content: str
    metadata: Optional[dict] = None

class Event(BaseModel):
    topic: str = Field(..., description="Topic of the event (e.g., app.auth.error)")
    event_id: str = Field(..., description="Unique and collision-resistant ID (e.g., UUID)")
    timestamp: datetime.datetime = Field(..., description="ISO8601 format.")
    source: str = Field(..., description="Source system/service name")
    payload: EventPayload

class ProcessedEvent(BaseModel):
    event_id: str
    topic: str
    timestamp: datetime.datetime

class AggregatorStats(BaseModel):
    received: int
    unique_processed: int
    duplicate_dropped: int
    topics: List[str]
    uptime: int