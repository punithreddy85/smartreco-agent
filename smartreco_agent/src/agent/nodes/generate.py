"""generate_and_verify - strong Mesh model + the grounding guarantee
(ARCHITECTURE.md \u00a79.2).

The generation prompt receives only the reranked candidate set, each product
rendered with its UUID. Before persisting, every cited product_id must be a
member of that set. On a second violation the run is abandoned and the
previous recommendation stays current - hallucinated courses are structurally
impossible, not merely discouraged.
"""

from __future__ import annotations

import time

from smartreco_agent.src.agent.prompts.narrative import build_narrative_prompt
from smartreco_agent.src.agent.schemas import Recommendation
from smartreco_agent.src.agent.state import AgentState, with_timing
from smartreco_agent.src.mesh.client import ParseFailure, complete_json
from smartreco_agent.src.settings import settings
from smartreco_agent.utils.pylogger import get_python_logger

logger = get_python_logger(settings.PYTHON_LOG_LEVEL)


async def _call(
    candidates, themes, journey_stage, violation_note=None
) -> tuple[Recommendation, tuple[int, int]]:
    system, user = build_narrative_prompt(
        themes=themes,
        journey_stage=journey_stage,
        candidates=candidates,
        violation_note=violation_note,
    )
    rec, usage = await complete_json(
        model=settings.MESH_CHAT_MODEL,
        system=system,
        user=user,
        schema=Recommendation,
        max_tokens=1200,
    )
    return rec, (usage.prompt_tokens, usage.completion_tokens)


async def generate_and_verify(state: AgentState) -> AgentState:
    t0 = time.monotonic()
    candidates = state.get("reranked") or []
    intent = state["intent"]
    assert intent is not None, (
        "generate_and_verify runs only after analyze_intent has populated state['intent']"
    )
    candidate_ids = {c["id"] for c in candidates}

    if not candidates:
        return {
            "recommendation": None,
            "error": "no candidates survived retrieval/rerank",
            "node_timings": with_timing(
                state, "generate_and_verify", time.monotonic() - t0
            ),
        }

    prompt_tokens_total, completion_tokens_total = (
        state.get("prompt_tokens", 0),
        state.get("completion_tokens", 0),
    )

    try:
        rec, (pt, ct) = await _call(candidates, intent.themes, intent.journey_stage)
        prompt_tokens_total, completion_tokens_total = (
            pt + prompt_tokens_total,
            ct + completion_tokens_total,
        )

        cited = {item.product_id for item in rec.items}
        if not cited.issubset(candidate_ids):
            violation = cited - candidate_ids
            logger.warning("grounding_violation_retry", violation=list(violation))
            rec, (pt, ct) = await _call(
                candidates,
                intent.themes,
                intent.journey_stage,
                violation_note=f"Your previous response referenced product_id(s) {sorted(violation)} which are NOT in the candidate list.",
            )
            prompt_tokens_total, completion_tokens_total = (
                pt + prompt_tokens_total,
                ct + completion_tokens_total,
            )
            cited = {item.product_id for item in rec.items}
            if not cited.issubset(candidate_ids):
                logger.error(
                    "grounding_violation_fail_closed",
                    violation=list(cited - candidate_ids),
                )
                return {
                    "recommendation": None,
                    "error": "grounding validator rejected hallucinated product_id after retry",
                    "prompt_tokens": prompt_tokens_total,
                    "completion_tokens": completion_tokens_total,
                    "node_timings": with_timing(
                        state, "generate_and_verify", time.monotonic() - t0
                    ),
                }

        return {
            "recommendation": rec,
            "prompt_tokens": prompt_tokens_total,
            "completion_tokens": completion_tokens_total,
            "node_timings": with_timing(
                state, "generate_and_verify", time.monotonic() - t0
            ),
        }

    except ParseFailure as e:
        logger.error("generation_parse_failure", error=str(e))
        return {
            "recommendation": None,
            "error": f"parse failure: {e}",
            "prompt_tokens": prompt_tokens_total,
            "completion_tokens": completion_tokens_total,
            "node_timings": with_timing(
                state, "generate_and_verify", time.monotonic() - t0
            ),
        }
