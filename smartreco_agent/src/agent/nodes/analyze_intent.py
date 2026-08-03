"""analyze_intent - cheap Mesh model, structured output (ARCHITECTURE.md \u00a79.1)."""

from __future__ import annotations

import time

from smartreco_agent.src.agent.prompts.intent import build_intent_prompt
from smartreco_agent.src.agent.schemas import IntentAnalysis
from smartreco_agent.src.agent.state import AgentState, add_tokens, with_timing
from smartreco_agent.src.mesh.client import complete_json
from smartreco_agent.src.settings import settings


async def analyze_intent(state: AgentState) -> AgentState:
    t0 = time.monotonic()
    profile = state.get("profile") or {}

    system, user = build_intent_prompt(
        weights=profile.get("weights") or {},
        recent_events=state.get("recent_events") or [],
        recent_search_queries=state.get("recent_search_queries") or [],
    )

    intent, usage = await complete_json(
        model=settings.MESH_CHEAP_MODEL,
        system=system,
        user=user,
        schema=IntentAnalysis,
        max_tokens=400,
    )

    prompt_tokens, completion_tokens = add_tokens(state, usage.prompt_tokens, usage.completion_tokens)

    return {
        "intent": intent,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "node_timings": with_timing(state, "analyze_intent", time.monotonic() - t0),
    }
