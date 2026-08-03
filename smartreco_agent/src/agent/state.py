"""Graph state. Every node returns a partial update (LangGraph merges dicts)."""

from __future__ import annotations

from typing import Any, Optional, TypedDict

from smartreco_agent.src.agent.schemas import IntentAnalysis, Recommendation
from smartreco_agent.src.vectors.protocol import ScoredProduct


class AgentState(TypedDict, total=False):
    user_id: str
    trigger_reason: str

    profile: dict[str, Any]
    recent_events: list[dict[str, Any]]
    recent_search_queries: list[str]
    excluded_product_ids: set[str]

    intent: Optional[IntentAnalysis]
    candidates: list[ScoredProduct]
    grade_passed: bool
    refine_loops: int

    reranked: list[
        dict[str, Any]
    ]  # ScoredProduct-ish dict + fused `score` + product row fields

    recommendation: Optional[Recommendation]

    node_timings: dict[str, float]
    prompt_tokens: int
    completion_tokens: int
    error: Optional[str]


def with_timing(state: AgentState, node: str, elapsed: float) -> dict[str, float]:
    """LangGraph replaces (rather than merges) a returned dict key by default,
    so every node folds its timing into the accumulated dict explicitly."""
    timings = dict(state.get("node_timings") or {})
    timings[node] = round(elapsed, 4)
    return timings


def add_tokens(
    state: AgentState, prompt_tokens: int, completion_tokens: int
) -> tuple[int, int]:
    return (
        state.get("prompt_tokens", 0) + prompt_tokens,
        state.get("completion_tokens", 0) + completion_tokens,
    )
