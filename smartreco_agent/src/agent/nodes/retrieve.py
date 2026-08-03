"""retrieve - no LLM. Multi-query fan-out + metadata pre-filter + MMR dedupe
(ARCHITECTURE.md \u00a79.3)."""

from __future__ import annotations

import time

import numpy as np

from smartreco_agent.src.agent.config import (
    MMR_LAMBDA,
    RETRIEVAL_CANDIDATES_PER_QUERY,
    RETRIEVAL_MAX_CANDIDATES,
)
from smartreco_agent.src.agent.state import AgentState, with_timing
from smartreco_agent.src.mesh.client import embed_query_cached
from smartreco_agent.src.vectors.pgvector_store import get_vector_store
from smartreco_agent.src.vectors.protocol import ScoredProduct, SearchFilters

LEVEL_BAND = {
    "beginner": ("beginner", "intermediate"),
    "intermediate": ("beginner", "intermediate", "advanced"),
    "advanced": ("intermediate", "advanced"),
}


async def _mmr_dedupe(
    candidates: list[ScoredProduct], limit: int
) -> list[ScoredProduct]:
    if len(candidates) <= 1:
        return candidates

    store = get_vector_store()
    embeddings = await store.get_embeddings([c.product_id for c in candidates])
    if not embeddings:
        return candidates[:limit]

    remaining = [c for c in candidates if c.product_id in embeddings]
    selected: list[ScoredProduct] = []
    selected_vectors: list[np.ndarray] = []

    while remaining and len(selected) < limit:
        best: ScoredProduct | None = None
        best_score = -1e9
        for c in remaining:
            vec = np.array(embeddings[c.product_id])
            diversity_penalty = 0.0
            if selected_vectors:
                sims = [
                    float(
                        np.dot(vec, sv)
                        / (np.linalg.norm(vec) * np.linalg.norm(sv) + 1e-9)
                    )
                    for sv in selected_vectors
                ]
                diversity_penalty = max(sims)
            mmr_score = MMR_LAMBDA * c.similarity - (1 - MMR_LAMBDA) * diversity_penalty
            if mmr_score > best_score:
                best, best_score = c, mmr_score
        assert best is not None, "remaining is non-empty per the while condition"
        selected.append(best)
        selected_vectors.append(np.array(embeddings[best.product_id]))
        remaining.remove(best)

    return selected


async def retrieve(state: AgentState) -> AgentState:
    t0 = time.monotonic()
    intent = state["intent"]
    assert intent is not None, (
        "retrieve runs only after analyze_intent has populated state['intent']"
    )
    profile = state.get("profile") or {}
    excluded = state.get("excluded_product_ids") or set()

    filters = SearchFilters(
        is_active=True,
        level_in=LEVEL_BAND.get(intent.level, ()),
        exclude_ids=tuple(excluded),
    )

    store = get_vector_store()
    by_id: dict[str, ScoredProduct] = {}

    for query_text in intent.retrieval_queries:
        query_vector = await embed_query_cached(query_text)
        results = await store.search(
            query_vector, RETRIEVAL_CANDIDATES_PER_QUERY, filters
        )
        for r in results:
            if (
                r.product_id not in by_id
                or r.similarity > by_id[r.product_id].similarity
            ):
                by_id[r.product_id] = r

    # The raw behavioural interest vector is an unconditional 5th query: if the
    # LLM misreads intent, the behaviour-derived signal still contributes.
    interest_vector = profile.get("interest_vector")
    if interest_vector:
        results = await store.search(
            interest_vector, RETRIEVAL_CANDIDATES_PER_QUERY, filters
        )
        for r in results:
            if (
                r.product_id not in by_id
                or r.similarity > by_id[r.product_id].similarity
            ):
                by_id[r.product_id] = r

    unioned = sorted(by_id.values(), key=lambda c: c.similarity, reverse=True)
    candidates = await _mmr_dedupe(unioned, RETRIEVAL_MAX_CANDIDATES)

    return {
        "candidates": candidates,
        "node_timings": with_timing(state, "retrieve", time.monotonic() - t0),
    }
