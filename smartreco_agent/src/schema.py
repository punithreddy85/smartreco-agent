"""Request/response models shared across routes.

Agent structured-output schemas (Mesh `response_format` contracts) live in
`smartreco_agent/src/agent/schemas.py` instead, since they are tightly coupled
to the LangGraph nodes that consume them.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

EventType = Literal[
    "page_view",
    "product_view",
    "search",
    "click",
    "dwell",
    "add_to_cart",
    "dismiss",
    "scroll",
]


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ProductIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    category: str = Field(min_length=1, max_length=80)
    level: Literal["beginner", "intermediate", "advanced"]
    price_cents: int = Field(ge=0)
    tags: list[str] = Field(default_factory=list)
    is_active: bool = True
    learning_outcomes: list[str] = Field(default_factory=list)
    duration_minutes: Optional[int] = Field(default=None, ge=0)
    module_count: Optional[int] = Field(default=None, ge=0)


class EventIn(BaseModel):
    event_id: UUID
    type: EventType
    product_id: Optional[UUID] = None
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime


class EventBatch(BaseModel):
    """Capped at 50 events and rate-limited per user - a hostile client cannot
    inflate its own interest model unboundedly (ARCHITECTURE.md \u00a713)."""

    session_id: UUID
    events: list[EventIn] = Field(min_length=1, max_length=50)


class IngestResponse(BaseModel):
    accepted: int


class SignalFeedItem(BaseModel):
    """One entry in the live "Your Signal" panel (GET /api/live-signal)."""

    label: str
    detail: str
    icon: str = "dot"
    is_latest: bool
    occurred_at: str = ""


class SignalRecommendationItem(BaseModel):
    product_id: str
    title: str
    category: str
    price_cents: int
    reason: str


class SignalRecommendation(BaseModel):
    narrative: str
    items: list[SignalRecommendationItem]
    trigger_reason: Optional[str] = None
    refreshed_at: Optional[str] = None


class InterestWeight(BaseModel):
    label: str
    pct: int


class LiveSignalResponse(BaseModel):
    """Response body for GET /api/live-signal - a pure read of already-computed
    state, never triggers agent generation (ARCHITECTURE.md \u00a76.1, \u00a715)."""

    feed: list[SignalFeedItem]
    recommendation: Optional[SignalRecommendation] = None
    events_since_gen: int = 0
    trigger_threshold: int = 3
    top_interests: list[InterestWeight] = Field(default_factory=list)
