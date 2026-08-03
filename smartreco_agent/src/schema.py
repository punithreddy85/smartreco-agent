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
    "page_view", "product_view", "search", "click", "dwell", "add_to_cart", "dismiss", "scroll"
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
