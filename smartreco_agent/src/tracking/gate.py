"""The trigger policy: decides when behaviour has moved enough to justify an
agent run (ARCHITECTURE.md \u00a78). This is the cost-control mechanism and the
part of the brief explicitly judged on efficiency.

Three tiers:
- Tier 0 (every event) lives in `tracking/profile.py` - pure SQL/numpy, free.
- Tier 1 (this module) is a deterministic gate evaluated after each batch.
- Tier 2 (the agent) runs only when this gate returns a non-None reason.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np

from smartreco_agent.src.db import catalog

COOLDOWN = timedelta(minutes=10)
COUNT_THRESHOLD = 8
DRIFT_THRESHOLD = 0.15  # cosine *distance* (1 - similarity)


def _top_category(weights: dict[str, float]) -> Optional[str]:
    category_weights = {
        k[len("category:") :]: v
        for k, v in weights.items()
        if k.startswith("category:")
    }
    if not category_weights:
        return None
    return max(category_weights.items(), key=lambda kv: kv[1])[0]


def _cosine_distance(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a, dtype=np.float64), np.array(b, dtype=np.float64)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    if denom < 1e-9:
        return 1.0
    return 1.0 - float(np.dot(va, vb) / denom)


async def should_generate(user_id: str, *, force: bool = False) -> Optional[str]:
    """Returns a trigger reason string, or None if the agent should not run."""
    profile = await catalog.get_profile(user_id)
    if profile is None:
        # `tracking.profile.apply()` always runs before the gate is consulted,
        # so this only fires if the gate is called standalone with no events yet.
        return None

    now = datetime.now(timezone.utc)
    last_generated_at = profile.get("last_generated_at")
    if last_generated_at and now - last_generated_at < COOLDOWN:
        return None  # cooldown is absolute - even an explicit refresh cannot bypass it

    if force:
        return "manual"

    current_rec = await catalog.get_current_recommendation(user_id)
    if current_rec and current_rec["profile_hash"] == profile.get("profile_hash"):
        return None  # nothing has materially moved since the last generation

    if profile.get("events_since_gen", 0) >= COUNT_THRESHOLD:
        return "count"

    interest_vector = profile.get("interest_vector")
    gen_vector = profile.get("gen_vector")
    if interest_vector and gen_vector:
        if _cosine_distance(interest_vector, gen_vector) > DRIFT_THRESHOLD:
            return "drift"

    if current_rec:
        top_category = _top_category(profile.get("weights") or {})
        current_categories = {item["category"] for item in current_rec.get("items", [])}
        if (
            top_category
            and current_categories
            and top_category not in current_categories
        ):
            return "category_shift"

    return None
