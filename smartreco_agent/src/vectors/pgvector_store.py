"""pgvector-backed implementation of the VectorStore protocol.

Lives in the `vectors` Postgres schema, in the same physical database as
`catalog` for operational simplicity, but touched only through this module -
see ARCHITECTURE.md \u00a75.1 for why that boundary is load-bearing rather than
cosmetic.
"""

from __future__ import annotations

from contextlib import AsyncExitStack
from typing import Sequence

from smartreco_agent.src.db.pool import get_connection
from smartreco_agent.src.vectors.protocol import (
    EmbeddedProduct,
    ScoredProduct,
    SearchFilters,
)


class PgVectorStore:
    async def upsert(self, items: Sequence[EmbeddedProduct]) -> None:
        if not items:
            return
        async with get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.executemany(
                    """
                    insert into vectors.product_embeddings
                        (product_id, embedding, content_hash, model, category, level, price_cents, is_active)
                    values (%s, %s, %s, %s, %s, %s, %s, %s)
                    on conflict (product_id) do update
                       set embedding = excluded.embedding,
                           content_hash = excluded.content_hash,
                           model = excluded.model,
                           category = excluded.category,
                           level = excluded.level,
                           price_cents = excluded.price_cents,
                           is_active = excluded.is_active,
                           updated_at = now()
                    """,
                    [
                        (
                            i.product_id, i.embedding, i.content_hash, i.model,
                            i.category, i.level, i.price_cents, i.is_active,
                        )
                        for i in items
                    ],
                )

    async def delete(self, product_ids: Sequence[str]) -> None:
        if not product_ids:
            return
        async with get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "delete from vectors.product_embeddings where product_id = any(%s)",
                    (list(product_ids),),
                )

    async def search(
        self, query: list[float], k: int, filters: SearchFilters
    ) -> list[ScoredProduct]:
        where = ["is_active = %s"] if filters.is_active else []
        params: list = [filters.is_active] if filters.is_active else []

        if filters.category:
            where.append("category = %s")
            params.append(filters.category)
        if filters.level_in:
            where.append("level = any(%s)")
            params.append(list(filters.level_in))
        if filters.max_price_cents is not None:
            where.append("price_cents <= %s")
            params.append(filters.max_price_cents)
        if filters.exclude_ids:
            where.append("product_id != all(%s)")
            params.append(list(filters.exclude_ids))

        clause = f"where {' and '.join(where)}" if where else ""

        async with AsyncExitStack() as stack:
            conn = await stack.enter_async_context(get_connection())
            async with conn.cursor() as cur:
                await cur.execute(
                    f"""
                    select product_id, category, level, price_cents,
                           1 - (embedding <=> %s) as similarity
                      from vectors.product_embeddings
                      {clause}
                     order by embedding <=> %s
                     limit %s
                    """,
                    [query, *params, query, k],
                )
                rows = await cur.fetchall()
                return [
                    ScoredProduct(
                        product_id=str(r["product_id"]),
                        similarity=float(r["similarity"]),
                        category=r["category"],
                        level=r["level"],
                        price_cents=r["price_cents"],
                    )
                    for r in rows
                ]

    async def all_hashes(self) -> dict[str, str]:
        async with get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("select product_id, content_hash from vectors.product_embeddings")
                rows = await cur.fetchall()
                return {str(r["product_id"]): r["content_hash"] for r in rows}

    async def get_embeddings(self, product_ids: Sequence[str]) -> dict[str, list[float]]:
        if not product_ids:
            return {}
        async with get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "select product_id, embedding from vectors.product_embeddings where product_id = any(%s)",
                    (list(product_ids),),
                )
                rows = await cur.fetchall()
                return {str(r["product_id"]): list(r["embedding"]) for r in rows}


_store: PgVectorStore | None = None


def get_vector_store() -> PgVectorStore:
    global _store
    if _store is None:
        _store = PgVectorStore()
    return _store
