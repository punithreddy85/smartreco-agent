"""Graph assembly + `run_agent`, the single entry point every caller uses
(ingest BackgroundTask, manual refresh, digest worker).

`run_agent` also implements the caching half of "efficient AI-call triggering
... and caching" from the brief: a scheduled digest run whose profile_hash has
not moved since the last generation reuses the existing recommendation and
records `cache_hit=True` on `agent_runs` without spending a single Mesh call.
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from smartreco_agent.src.agent.nodes.analyze_intent import analyze_intent
from smartreco_agent.src.agent.nodes.generate import generate_and_verify
from smartreco_agent.src.agent.nodes.grade import grade, route_after_grade
from smartreco_agent.src.agent.nodes.load_signals import load_signals
from smartreco_agent.src.agent.nodes.persist import persist
from smartreco_agent.src.agent.nodes.refine import refine
from smartreco_agent.src.agent.nodes.rerank import rerank
from smartreco_agent.src.agent.nodes.retrieve import retrieve
from smartreco_agent.src.agent.state import AgentState
from smartreco_agent.src.db import catalog
from smartreco_agent.src.mesh.client import MeshError
from smartreco_agent.src.settings import settings
from smartreco_agent.utils.pylogger import get_python_logger

logger = get_python_logger(settings.PYTHON_LOG_LEVEL)

_graph = None


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("load_signals", load_signals)
    graph.add_node("analyze_intent", analyze_intent)
    graph.add_node("retrieve", retrieve)
    graph.add_node("grade", grade)
    graph.add_node("refine", refine)
    graph.add_node("rerank", rerank)
    graph.add_node("generate_and_verify", generate_and_verify)
    graph.add_node("persist", persist)

    graph.set_entry_point("load_signals")
    graph.add_edge("load_signals", "analyze_intent")
    graph.add_edge("analyze_intent", "retrieve")
    graph.add_edge("retrieve", "grade")
    graph.add_conditional_edges("grade", route_after_grade, {"refine": "refine", "rerank": "rerank"})
    graph.add_edge("refine", "retrieve")
    graph.add_edge("rerank", "generate_and_verify")
    graph.add_edge("generate_and_verify", "persist")
    graph.add_edge("persist", END)

    return graph.compile()


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


async def run_agent(user_id: str, trigger_reason: str) -> dict | None:
    """Runs the recommendation graph for `user_id`. Never raises: any failure
    is recorded on `agent_runs` and the previous recommendation stays current
    (ARCHITECTURE.md \u00a714 - "no Mesh failure is ever surfaced to a user")."""
    profile = await catalog.get_profile(user_id)
    if not profile or not profile.get("interest_vector"):
        logger.info("agent_skipped_no_signal", user_id=user_id)
        return None

    current_rec = await catalog.get_current_recommendation(user_id)
    if (
        current_rec
        and trigger_reason == "scheduled"
        and current_rec["profile_hash"] == profile.get("profile_hash")
    ):
        await catalog.insert_agent_run(
            user_id=user_id, trigger_reason=trigger_reason, cache_hit=True,
            model=settings.MESH_CHAT_MODEL,
        )
        logger.info("agent_cache_hit", user_id=user_id, trigger_reason=trigger_reason)
        return current_rec

    initial_state: AgentState = {
        "user_id": user_id,
        "trigger_reason": trigger_reason,
        "refine_loops": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
    }

    try:
        result = await get_graph().ainvoke(initial_state)
    except MeshError as e:
        logger.error("agent_run_failed", user_id=user_id, error=str(e))
        await catalog.insert_agent_run(
            user_id=user_id, trigger_reason=trigger_reason, error=str(e),
            model=settings.MESH_CHAT_MODEL,
        )
        return current_rec
    except Exception as e:  # noqa: BLE001 - the agent must never crash the caller
        logger.error("agent_run_unexpected_failure", user_id=user_id, error=str(e), exc_info=True)
        await catalog.insert_agent_run(
            user_id=user_id, trigger_reason=trigger_reason, error=f"unexpected: {e}",
            model=settings.MESH_CHAT_MODEL,
        )
        return current_rec

    if result.get("recommendation") is None:
        return current_rec
    return await catalog.get_current_recommendation(user_id)
