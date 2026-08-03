"""rerank - no LLM. Score fusion over the graded candidate set (ARCHITECTURE.md \u00a79.3).

No cross-encoder: at catalog sizes in the tens of items the gain does not
justify a second model call.
"""

from __future__ import annotations

import math
import time
from datetime import datetime, timezone

from smartreco_agent.src.agent.config import RERANK_TOP_N, SCORE_WEIGHTS
from smartreco_agent.src.agent.state import AgentState, with_timing
from smartreco_agent.src.db import catalog

RECENCY_TAU_HOURS = 24.0
POPULARITY_PRIOR = 0.5  # placeholder: no enrolment/popularity data source exists yet


def _category_match(category: str, weights: dict[str, float]) -> float:
    category_weights = {
        k[len("category:") :]: v
        for k, v in weights.items()
        if k.startswith("category:")
    }
    if not category_weights:
        return 0.0
    max_weight = max(category_weights.values())
    if max_weight <= 0:
        return 0.0
    return max(category_weights.get(category, 0.0), 0.0) / max_weight


async def _recency_by_category(
    recent_events: list[dict], now: datetime
) -> dict[str, float]:
    product_ids = {str(e["product_id"]) for e in recent_events if e.get("product_id")}
    if not product_ids:
        return {}
    products = {
        str(p["id"]): p for p in await catalog.get_products_by_ids(list(product_ids))
    }

    most_recent_by_category: dict[str, datetime] = {}
    for e in recent_events:
        pid = str(e["product_id"]) if e.get("product_id") else None
        if not pid or pid not in products:
            continue
        category = products[pid]["category"]
        occurred_at = e["occurred_at"]
        if (
            category not in most_recent_by_category
            or occurred_at > most_recent_by_category[category]
        ):
            most_recent_by_category[category] = occurred_at

    return {
        category: math.exp(
            -max((now - ts).total_seconds() / 3600.0, 0.0) / RECENCY_TAU_HOURS
        )
        for category, ts in most_recent_by_category.items()
    }


async def rerank(state: AgentState) -> AgentState:
    t0 = time.monotonic()
    candidates = state.get("candidates") or []
    weights = (state.get("profile") or {}).get("weights") or {}
    now = datetime.now(timezone.utc)

    recency_by_category = await _recency_by_category(
        state.get("recent_events") or [], now
    )

    scored = []
    for c in candidates:
        similarity = max(c.similarity, 0.0)
        category_match = _category_match(c.category, weights)
        recency = recency_by_category.get(c.category, 0.0)
        fused = (
            SCORE_WEIGHTS["similarity"] * similarity
            + SCORE_WEIGHTS["category_match"] * category_match
            + SCORE_WEIGHTS["recency"] * recency
            + SCORE_WEIGHTS["popularity"] * POPULARITY_PRIOR
        )
        scored.append((fused, c))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    top = scored[:RERANK_TOP_N]

    products = {
        str(p["id"]): p
        for p in await catalog.get_products_by_ids([c.product_id for _, c in top])
    }

    reranked = []
    for fused_score, c in top:
        product = products.get(c.product_id)
        if not product:
            continue
        reranked.append(
            {
                "id": str(product["id"]),
                "title": product["title"],
                "description": product["description"],
                "category": product["category"],
                "level": product["level"],
                "price_cents": product["price_cents"],
                "score": round(fused_score, 4),
            }
        )

    return {
        "reranked": reranked,
        "node_timings": with_timing(state, "rerank", time.monotonic() - t0),
    }
