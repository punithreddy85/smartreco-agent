"""load_signals - no LLM. Loads everything downstream nodes need."""

from __future__ import annotations

import time

from smartreco_agent.src.agent.state import AgentState, with_timing
from smartreco_agent.src.db import catalog


async def load_signals(state: AgentState) -> AgentState:
    t0 = time.monotonic()
    user_id = state["user_id"]
    trigger_reason = state.get("trigger_reason")

    profile = await catalog.get_profile(user_id) or {}
    recent_events = await catalog.recent_events(user_id, limit=30)
    recent_search_queries = await catalog.recent_search_queries(user_id, limit=10)
    excluded = await catalog.dismissed_and_owned_product_ids(user_id)

    # The product the user is currently looking at is, by definition, the
    # closest vector match right after their interest vector is updated by
    # viewing it - exclude it or it will almost always rank first (P0.1).
    current_product_id = next(
        (
            str(event["product_id"])
            for event in recent_events
            if event["type"] == "product_view" and event.get("product_id")
        ),
        None,
    )
    if current_product_id:
        excluded = excluded | {current_product_id}

    # Re-recommending the identical set right after a `count` trigger reads
    # as the agent doing nothing. `drift`/`category_shift` are allowed to
    # repeat a pick - a stable recommendation is meaningful there.
    if trigger_reason == "count":
        excluded = excluded | await catalog.current_recommendation_product_ids(user_id)

    return {
        "profile": profile,
        "recent_events": recent_events,
        "recent_search_queries": recent_search_queries,
        "current_product_id": current_product_id,
        "excluded_product_ids": excluded,
        "node_timings": with_timing(state, "load_signals", time.monotonic() - t0),
    }
