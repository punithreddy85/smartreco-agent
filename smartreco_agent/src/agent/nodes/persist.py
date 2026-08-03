"""persist - no LLM. Writes the recommendation, flips `is_current`, resets the
drift baseline, and records the agent_runs evidence row (ARCHITECTURE.md \u00a79.1)."""

from __future__ import annotations

import time

from smartreco_agent.src.agent.schemas import PROMPT_VERSION
from smartreco_agent.src.agent.state import AgentState, with_timing
from smartreco_agent.src.db import catalog
from smartreco_agent.src.db.pool import transaction
from smartreco_agent.src.settings import settings


async def persist(state: AgentState) -> AgentState:
    t0 = time.monotonic()
    user_id = state["user_id"]
    profile = state.get("profile") or {}
    recommendation = state.get("recommendation")
    candidates = state.get("candidates") or []

    if recommendation is None:
        await catalog.insert_agent_run(
            user_id=user_id,
            trigger_reason=state.get("trigger_reason", "unknown"),
            cache_hit=False,
            refine_loops=state.get("refine_loops", 0),
            retrieved_ids=[c.product_id for c in candidates],
            node_timings=state.get("node_timings") or {},
            model=settings.MESH_CHAT_MODEL,
            prompt_tokens=state.get("prompt_tokens", 0),
            completion_tokens=state.get("completion_tokens", 0),
            error=state.get("error") or "generation failed",
        )
        return {"node_timings": with_timing(state, "persist", time.monotonic() - t0)}

    score_by_id = {c["id"]: c["score"] for c in (state.get("reranked") or [])}
    profile_hash_value = profile.get("profile_hash") or ""

    async with transaction() as conn:
        await catalog.persist_recommendation(
            user_id=user_id,
            narrative=recommendation.narrative,
            trigger_reason=state.get("trigger_reason", "unknown"),
            profile_hash_value=profile_hash_value,
            model=settings.MESH_CHAT_MODEL,
            prompt_version=PROMPT_VERSION,
            items=[
                {
                    "product_id": item.product_id,
                    "reason": item.reason,
                    "score": score_by_id.get(item.product_id, 0.0),
                }
                for item in recommendation.items
            ],
            conn=conn,
        )
        await catalog.mark_generated(
            user_id,
            gen_vector=profile.get("interest_vector"),
            profile_hash_value=profile_hash_value,
            conn=conn,
        )

    await catalog.insert_agent_run(
        user_id=user_id,
        trigger_reason=state.get("trigger_reason", "unknown"),
        cache_hit=False,
        refine_loops=state.get("refine_loops", 0),
        retrieved_ids=[c.product_id for c in candidates],
        node_timings=state.get("node_timings") or {},
        model=settings.MESH_CHAT_MODEL,
        prompt_tokens=state.get("prompt_tokens", 0),
        completion_tokens=state.get("completion_tokens", 0),
        error=None,
    )

    return {"node_timings": with_timing(state, "persist", time.monotonic() - t0)}
