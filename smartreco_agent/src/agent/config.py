"""Tunable knobs for retrieval and rerank, isolated in one place so a weight
can be changed without touching retrieval code (ARCHITECTURE.md \u00a79.3)."""

from __future__ import annotations

RETRIEVAL_CANDIDATES_PER_QUERY = 8
RETRIEVAL_MAX_CANDIDATES = 20
MMR_LAMBDA = 0.7

GRADE_MIN_MEAN_TOP5_SIMILARITY = 0.35
GRADE_MIN_DISTINCT_CATEGORIES = 3
GRADE_MIN_CANDIDATES = 8
MAX_REFINE_LOOPS = 1

RERANK_TOP_N = 4

# Score fusion weights (must sum to 1.0). Order: cosine similarity, category
# weight match (from the decayed interest weights), recency of related
# interest, popularity prior (log-scaled, breaks ties only - no real
# popularity signal exists yet, so this stays at a small constant per item).
SCORE_WEIGHTS = {
    "similarity": 0.55,
    "category_match": 0.20,
    "recency": 0.15,
    "popularity": 0.10,
}
