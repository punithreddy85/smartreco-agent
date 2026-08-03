"""Structured-output contracts for the two Mesh chat nodes.

`extra="forbid"` makes Pydantic emit `additionalProperties: false`, which Mesh
enforces provider-side via `response_format={"type": "json_schema", ...}`
regardless of prompt wording (Appendix D.3).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PROMPT_VERSION = "v1"


class IntentAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    themes: list[str] = Field(min_length=1, max_length=5)
    level: Literal["beginner", "intermediate", "advanced"]
    journey_stage: str
    retrieval_queries: list[str] = Field(min_length=2, max_length=4)


class RefinedQueries(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retrieval_queries: list[str] = Field(min_length=2, max_length=4)
    reasoning: str


class RecommendedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str  # MUST be a member of the retrieved candidate set
    reason: str


class Recommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    narrative: str
    items: list[RecommendedItem] = Field(min_length=1, max_length=4)
