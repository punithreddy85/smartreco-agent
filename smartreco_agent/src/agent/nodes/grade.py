"""grade - no LLM. Heuristic check on retrieval quality (ARCHITECTURE.md \u00a79.1)."""

from __future__ import annotations

import time

from smartreco_agent.src.agent.config import (
    GRADE_MIN_CANDIDATES,
    GRADE_MIN_DISTINCT_CATEGORIES,
    GRADE_MIN_MEAN_TOP5_SIMILARITY,
    MAX_REFINE_LOOPS,
)
from smartreco_agent.src.agent.state import AgentState, with_timing


def grade_reasons(state: AgentState) -> list[str]:
    candidates = state.get("candidates") or []
    reasons = []
    if len(candidates) < GRADE_MIN_CANDIDATES:
        reasons.append(f"only {len(candidates)} candidates retrieved (need >= {GRADE_MIN_CANDIDATES})")
    top5 = candidates[:5]
    mean_top5 = sum(c.similarity for c in top5) / len(top5) if top5 else 0.0
    if mean_top5 < GRADE_MIN_MEAN_TOP5_SIMILARITY:
        reasons.append(f"mean top-5 similarity {mean_top5:.2f} is below {GRADE_MIN_MEAN_TOP5_SIMILARITY}")
    distinct_categories = {c.category for c in candidates}
    if len(distinct_categories) < GRADE_MIN_DISTINCT_CATEGORIES:
        reasons.append(f"only {len(distinct_categories)} distinct categories (need >= {GRADE_MIN_DISTINCT_CATEGORIES})")
    return reasons


async def grade(state: AgentState) -> AgentState:
    t0 = time.monotonic()
    reasons = grade_reasons(state)
    return {
        "grade_passed": len(reasons) == 0,
        "node_timings": with_timing(state, "grade", time.monotonic() - t0),
    }


def route_after_grade(state: AgentState) -> str:
    """Conditional edge: refine at most once, then always proceed to rerank."""
    if state.get("grade_passed"):
        return "rerank"
    if state.get("refine_loops", 0) >= MAX_REFINE_LOOPS:
        return "rerank"
    return "refine"
