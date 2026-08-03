"""The VectorStore protocol - the only door into the `vectors` schema.

No cross-schema join, no foreign key to `catalog.products` anywhere. Divergence
between the two stores is therefore a real possibility, which is exactly why
`reconcile()` in `smartreco_agent/src/cron/reconcile.py` exists and is tested
(ARCHITECTURE.md \u00a75.1, \u00a75.4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol, Sequence

Vector = list[float]


@dataclass(frozen=True)
class EmbeddedProduct:
    product_id: str
    embedding: Vector
    content_hash: str
    model: str
    category: str
    level: str
    price_cents: int
    is_active: bool = True


@dataclass(frozen=True)
class SearchFilters:
    is_active: bool = True
    category: Optional[str] = None
    level_in: Sequence[str] = field(default_factory=tuple)
    max_price_cents: Optional[int] = None
    exclude_ids: Sequence[str] = field(default_factory=tuple)


@dataclass(frozen=True)
class ScoredProduct:
    product_id: str
    similarity: float
    category: str
    level: str
    price_cents: int


class VectorStore(Protocol):
    async def upsert(self, items: Sequence[EmbeddedProduct]) -> None: ...

    async def delete(self, product_ids: Sequence[str]) -> None: ...

    async def search(
        self, query: Vector, k: int, filters: SearchFilters
    ) -> list[ScoredProduct]: ...

    async def all_hashes(self) -> dict[str, str]: ...

    async def get_embeddings(self, product_ids: Sequence[str]) -> dict[str, Vector]: ...
