"""Transactional outbox for `catalog.products` -> `vectors.product_embeddings` sync.

Admin CRUD writes the product row and the outbox row in one transaction
(ARCHITECTURE.md \u00a75.2), so a crash between the two writes is impossible. The
drainer (`smartreco_agent/src/cron/outbox_drainer.py`) claims pending rows with
`FOR UPDATE SKIP LOCKED`, which makes concurrent drainer invocations safe -
this matters on serverless, where two cron ticks can overlap.
"""

from __future__ import annotations

from contextlib import AsyncExitStack
from typing import Any, Literal, Sequence
from uuid import UUID

from smartreco_agent.src.db.pool import get_connection

Op = Literal["upsert", "delete"]


async def _conn_or_borrow(stack: AsyncExitStack, conn):
    if conn is not None:
        return conn
    return await stack.enter_async_context(get_connection())


async def enqueue(product_id: UUID | str, op: Op, conn=None) -> None:
    async with AsyncExitStack() as stack:
        c = await _conn_or_borrow(stack, conn)
        async with c.cursor() as cur:
            await cur.execute(
                "insert into catalog.vector_outbox (product_id, op) values (%s, %s)",
                (str(product_id), op),
            )


async def enqueue_many(product_ids: Sequence[UUID | str], op: Op, conn=None) -> int:
    if not product_ids:
        return 0
    async with AsyncExitStack() as stack:
        c = await _conn_or_borrow(stack, conn)
        async with c.cursor() as cur:
            await cur.executemany(
                "insert into catalog.vector_outbox (product_id, op) values (%s, %s)",
                [(str(p), op) for p in product_ids],
            )
            return len(product_ids)


async def claim_pending(limit: int = 50, conn=None) -> list[dict[str, Any]]:
    """Claim up to `limit` pending rows, skipping any locked by a concurrent drainer."""
    async with AsyncExitStack() as stack:
        c = await _conn_or_borrow(stack, conn)
        async with c.cursor() as cur:
            await cur.execute(
                """
                select * from catalog.vector_outbox
                 where status = 'pending'
                 order by created_at
                 limit %s
                 for update skip locked
                """,
                (limit,),
            )
            return await cur.fetchall()


async def mark_done(outbox_id: int, conn=None) -> None:
    async with AsyncExitStack() as stack:
        c = await _conn_or_borrow(stack, conn)
        async with c.cursor() as cur:
            await cur.execute(
                "update catalog.vector_outbox set status = 'done' where id = %s",
                (outbox_id,),
            )


async def mark_failed(outbox_id: int, error: str, *, max_attempts: int = 5, conn=None) -> None:
    async with AsyncExitStack() as stack:
        c = await _conn_or_borrow(stack, conn)
        async with c.cursor() as cur:
            await cur.execute(
                """
                update catalog.vector_outbox
                   set attempts = attempts + 1,
                       last_error = %s,
                       status = case when attempts + 1 > %s then 'failed' else 'pending' end
                 where id = %s
                """,
                (error, max_attempts, outbox_id),
            )
