"""Decayed interest weights + interest vector, updated on every event batch.

Pure SQL + numpy, no LLM call - this is Tier 0 of the trigger policy and must
stay free (ARCHITECTURE.md \u00a78). The only external call in this module is an
embedding call for search-query text, and it only ever happens from a
BackgroundTask *after* the ingest response has already been returned, so it
never sits in a request path a user waits on.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

import numpy as np

from smartreco_agent.src.db import catalog
from smartreco_agent.src.db.hashing import profile_hash as compute_profile_hash
from smartreco_agent.src.mesh.client import embed_query_cached
from smartreco_agent.src.settings import settings
from smartreco_agent.src.vectors.pgvector_store import get_vector_store
from smartreco_agent.utils.pylogger import get_python_logger

logger = get_python_logger(settings.PYTHON_LOG_LEVEL)

TAU_HOURS = 72.0

EVENT_WEIGHT: dict[str, float] = {
    "page_view": 0.2,
    "product_view": 1.0,
    "search": 1.5,
    "click": 0.8,
    "dwell": 1.2,
    "add_to_cart": 3.0,
    "dismiss": -2.0,
}

DWELL_MIN_SECONDS = 30


def _decay_factor(hours_elapsed: float) -> float:
    return math.exp(-max(hours_elapsed, 0.0) / TAU_HOURS)


def _decay_all(weights: dict[str, float], hours_elapsed: float) -> dict[str, float]:
    factor = _decay_factor(hours_elapsed)
    return {k: v * factor for k, v in weights.items()}


def _event_weight(event: dict[str, Any]) -> float:
    base = EVENT_WEIGHT.get(event["type"], 0.0)
    if event["type"] == "dwell":
        # tracker.js's flushDwell() sends {"seconds": ...} (see static/tracker.js).
        seconds = (event.get("payload") or {}).get("seconds", 0)
        return base if seconds >= DWELL_MIN_SECONDS else 0.0
    return base


async def apply(user_id: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    """Update `catalog.user_profiles` for `user_id` from a freshly-ingested
    event batch. Returns the updated profile row."""
    profile = await catalog.get_profile(user_id)
    now = datetime.now(timezone.utc)

    if profile and profile.get("updated_at"):
        hours_elapsed = (now - profile["updated_at"]).total_seconds() / 3600.0
    else:
        hours_elapsed = 0.0

    weights: dict[str, float] = dict((profile or {}).get("weights") or {})
    weights = _decay_all(weights, hours_elapsed)

    old_vector = np.array(
        (profile or {}).get("interest_vector") or [], dtype=np.float64
    )
    vector_contribution = np.zeros(settings.MESH_EMBED_DIMENSIONS, dtype=np.float64)
    has_contribution = False

    product_ids = {str(e["product_id"]) for e in events if e.get("product_id")}
    products_by_id = (
        {str(p["id"]): p for p in await catalog.get_products_by_ids(list(product_ids))}
        if product_ids
        else {}
    )
    embeddings_by_id = (
        await get_vector_store().get_embeddings(list(products_by_id.keys()))
        if products_by_id
        else {}
    )

    countable_events = 0

    for event in events:
        w = _event_weight(event)
        if w == 0.0 and event["type"] != "search":
            continue
        countable_events += 1

        product = (
            products_by_id.get(str(event["product_id"]))
            if event.get("product_id")
            else None
        )

        if product:
            weights[f"category:{product['category']}"] = (
                weights.get(f"category:{product['category']}", 0.0) + w
            )
            for tag in product.get("tags") or []:
                weights[f"tag:{tag}"] = weights.get(f"tag:{tag}", 0.0) + w

            embedding = embeddings_by_id.get(str(product["id"]))
            if embedding is not None and w > 0:
                vector_contribution += w * np.array(embedding, dtype=np.float64)
                has_contribution = True

        if event["type"] == "search":
            query = (event.get("payload") or {}).get("query", "").strip()
            if query:
                weights[f"query:{query.lower()}"] = (
                    weights.get(f"query:{query.lower()}", 0.0) + w
                )
                try:
                    query_embedding = await embed_query_cached(query)
                    vector_contribution += EVENT_WEIGHT["search"] * np.array(
                        query_embedding, dtype=np.float64
                    )
                    has_contribution = True
                except Exception as e:  # noqa: BLE001 - never fail the whole batch on an embedding hiccup
                    logger.warning("search_embed_failed", error=str(e), query=query)

    decayed_old_vector = (
        old_vector * _decay_factor(hours_elapsed) if old_vector.size else old_vector
    )
    if decayed_old_vector.size and has_contribution:
        combined = decayed_old_vector + vector_contribution
    elif has_contribution:
        combined = vector_contribution
    elif decayed_old_vector.size:
        combined = decayed_old_vector
    else:
        combined = None

    new_vector = None
    if combined is not None:
        norm = np.linalg.norm(combined)
        if norm > 1e-9:
            new_vector = (combined / norm).tolist()

    new_hash = compute_profile_hash(weights)

    return await catalog.upsert_profile(
        user_id,
        weights=weights,
        interest_vector=new_vector,
        events_since_gen_delta=countable_events,
        profile_hash_value=new_hash,
    )
