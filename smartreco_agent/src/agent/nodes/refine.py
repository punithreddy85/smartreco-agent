"""refine - cheap Mesh model. Hard-capped at one loop by `route_after_grade`
(ARCHITECTURE.md \u00a79.1)."""

from __future__ import annotations

import time

from smartreco_agent.src.agent.nodes.grade import grade_reasons
from smartreco_agent.src.agent.prompts.intent import build_refine_prompt
from smartreco_agent.src.agent.schemas import RefinedQueries
from smartreco_agent.src.agent.state import AgentState, add_tokens, with_timing
from smartreco_agent.src.mesh.client import complete_json
from smartreco_agent.src.settings import settings


async def refine(state: AgentState) -> AgentState:
    t0 = time.monotonic()
    intent = state["intent"]
    reasons = grade_reasons(state)

    system, user = build_refine_prompt(previous_queries=intent.retrieval_queries, grade_reasons=reasons)

    refined, usage = await complete_json(
        model=settings.MESH_CHEAP_MODEL,
        system=system,
        user=user,
        schema=RefinedQueries,
        max_tokens=300,
    )

    prompt_tokens, completion_tokens = add_tokens(state, usage.prompt_tokens, usage.completion_tokens)
    new_intent = intent.model_copy(update={"retrieval_queries": refined.retrieval_queries})

    return {
        "intent": new_intent,
        "refine_loops": state.get("refine_loops", 0) + 1,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "node_timings": with_timing(state, "refine", time.monotonic() - t0),
    }
