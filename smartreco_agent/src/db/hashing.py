"""Content-hash and profile-hash helpers shared by catalog and vectors code.

Two hashes carry disproportionate weight in this system (ARCHITECTURE.md \u00a74.3):

- `content_hash` is a sha256 over the fields that are actually embedded. Editing
  `price_cents` does not change it, so a price-only edit costs zero embedding
  calls. It also doubles as the diff key reconciliation uses to detect drift
  between `catalog.products` and `vectors.product_embeddings`.
- `profile_hash` is a sha256 over the rounded top-K interest weights. An
  unchanged hash means the user's interests have not materially moved, so the
  trigger gate can skip the agent entirely without touching a vector.
"""

from __future__ import annotations

import hashlib
import json
from typing import Mapping, Sequence


def content_hash(
    *,
    title: str,
    description: str,
    category: str,
    level: str,
    tags: Sequence[str],
    learning_outcomes: Sequence[str] = (),
) -> str:
    """Sha256 over the embeddable fields of a product."""
    normalized_tags = "|".join(sorted(tags))
    normalized_outcomes = "|".join(o.strip() for o in learning_outcomes)
    payload = "||".join(
        [
            title.strip(),
            description.strip(),
            category.strip(),
            level.strip(),
            normalized_tags,
            normalized_outcomes,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def embeddable_text(
    *,
    title: str,
    description: str,
    category: str,
    level: str,
    tags: Sequence[str],
    learning_outcomes: Sequence[str] = (),
) -> str:
    """The text that is actually sent to the embedding model for a product."""
    tag_text = ", ".join(tags)
    outcomes_text = " ".join(learning_outcomes)
    header = f"{title}\n\nCategory: {category} | Level: {level} | Tags: {tag_text}"
    if outcomes_text:
        header += f"\n\nWhat you'll learn: {outcomes_text}"
    return f"{header}\n\n{description}"


def profile_hash(
    weights: Mapping[str, float], *, top_k: int = 12, precision: int = 2
) -> str:
    """Sha256 over the rounded top-K interest weights, order-independent."""
    top = sorted(weights.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
    rounded = {k: round(v, precision) for k, v in top if round(v, precision) != 0}
    canonical = json.dumps(rounded, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
