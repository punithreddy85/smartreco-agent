"""load_signals - no LLM. Loads everything downstream nodes need."""

from __future__ import annotations

import time

from smartreco_agent.src.agent.state import AgentState, with_timing
from smartreco_agent.src.db import catalog


async def load_signals(state: AgentState) -> AgentState:
    t0 = time.monotonic()
    user_id = state["user_id"]

    profile = await catalog.get_profile(user_id) or {}
    recent_events = await catalog.recent_events(user_id, limit=30)
    recent_search_queries = await catalog.recent_search_queries(user_id, limit=10)
    excluded = await catalog.dismissed_and_owned_product_ids(user_id)

    return {
        "profile": profile,
        "recent_events": recent_events,
        "recent_search_queries": recent_search_queries,
        "excluded_product_ids": excluded,
        "node_timings": with_timing(state, "load_signals", time.monotonic() - t0),
    }
