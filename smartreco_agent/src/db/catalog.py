"""Queries against the `catalog` schema: users, products, events, profiles,
recommendations, and agent_runs.

Every function accepts an optional `conn`. When omitted, a connection is
borrowed from the pool for the duration of the call; when provided (typically
from `db.pool.transaction()`), the caller controls the commit boundary - this
is what makes the product write + outbox enqueue atomic (ARCHITECTURE.md \u00a75.2).
"""

from __future__ import annotations

from contextlib import AsyncExitStack
from datetime import datetime
from typing import Any, Optional, Sequence
from uuid import UUID

from psycopg.types.json import Jsonb

from smartreco_agent.src.db.hashing import content_hash
from smartreco_agent.src.db.pool import get_connection


async def _conn_or_borrow(stack: AsyncExitStack, conn):
    if conn is not None:
        return conn
    return await stack.enter_async_context(get_connection())


# --------------------------------------------------------------------------- #
# Users
# --------------------------------------------------------------------------- #


async def create_user(
    email: str, password_hash: str, role: str = "user", conn=None
) -> dict[str, Any]:
    async with AsyncExitStack() as stack:
        c = await _conn_or_borrow(stack, conn)
        async with c.cursor() as cur:
            await cur.execute(
                """
                insert into catalog.users (email, password_hash, role)
                values (%s, %s, %s)
                returning id, email, role, created_at
                """,
                (email, password_hash, role),
            )
            return await cur.fetchone()


async def get_user_by_email(email: str, conn=None) -> Optional[dict[str, Any]]:
    async with AsyncExitStack() as stack:
        c = await _conn_or_borrow(stack, conn)
        async with c.cursor() as cur:
            await cur.execute(
                "select id, email, password_hash, role, created_at from catalog.users where email = %s",
                (email,),
            )
            return await cur.fetchone()


async def get_user_by_id(user_id: UUID | str, conn=None) -> Optional[dict[str, Any]]:
    async with AsyncExitStack() as stack:
        c = await _conn_or_borrow(stack, conn)
        async with c.cursor() as cur:
            await cur.execute(
                "select id, email, role, created_at from catalog.users where id = %s",
                (str(user_id),),
            )
            return await cur.fetchone()


# --------------------------------------------------------------------------- #
# Products
# --------------------------------------------------------------------------- #


async def list_products(
    *, active_only: bool = True, category: Optional[str] = None, conn=None
) -> list[dict[str, Any]]:
    where = ["is_active"] if active_only else []
    params: list[Any] = []
    if category:
        where.append("category = %s")
        params.append(category)
    clause = f"where {' and '.join(where)}" if where else ""
    async with AsyncExitStack() as stack:
        c = await _conn_or_borrow(stack, conn)
        async with c.cursor() as cur:
            await cur.execute(
                f"select * from catalog.products {clause} order by created_at desc",
                params,
            )
            return await cur.fetchall()


async def get_product(product_id: UUID | str, conn=None) -> Optional[dict[str, Any]]:
    async with AsyncExitStack() as stack:
        c = await _conn_or_borrow(stack, conn)
        async with c.cursor() as cur:
            await cur.execute(
                "select * from catalog.products where id = %s", (str(product_id),)
            )
            return await cur.fetchone()


async def get_products_by_ids(
    product_ids: Sequence[UUID | str], conn=None
) -> list[dict[str, Any]]:
    if not product_ids:
        return []
    async with AsyncExitStack() as stack:
        c = await _conn_or_borrow(stack, conn)
        async with c.cursor() as cur:
            await cur.execute(
                "select * from catalog.products where id = any(%s)",
                ([str(p) for p in product_ids],),
            )
            return await cur.fetchall()


async def upsert_product(
    *,
    product_id: Optional[UUID | str],
    title: str,
    description: str,
    category: str,
    level: str,
    price_cents: int,
    tags: Sequence[str],
    is_active: bool = True,
    conn=None,
) -> dict[str, Any]:
    """Insert or update a product. `content_hash` is computed here, never trusted from a caller."""
    hash_value = content_hash(
        title=title, description=description, category=category, level=level, tags=tags
    )
    async with AsyncExitStack() as stack:
        c = await _conn_or_borrow(stack, conn)
        async with c.cursor() as cur:
            if product_id is None:
                await cur.execute(
                    """
                    insert into catalog.products
                        (title, description, category, level, price_cents, tags, is_active, content_hash)
                    values (%s, %s, %s, %s, %s, %s, %s, %s)
                    returning *
                    """,
                    (
                        title,
                        description,
                        category,
                        level,
                        price_cents,
                        list(tags),
                        is_active,
                        hash_value,
                    ),
                )
            else:
                await cur.execute(
                    """
                    update catalog.products
                       set title = %s, description = %s, category = %s, level = %s,
                           price_cents = %s, tags = %s, is_active = %s, content_hash = %s,
                           updated_at = now()
                     where id = %s
                    returning *
                    """,
                    (
                        title,
                        description,
                        category,
                        level,
                        price_cents,
                        list(tags),
                        is_active,
                        hash_value,
                        str(product_id),
                    ),
                )
            return await cur.fetchone()


async def delete_product(product_id: UUID | str, conn=None) -> None:
    async with AsyncExitStack() as stack:
        c = await _conn_or_borrow(stack, conn)
        async with c.cursor() as cur:
            await cur.execute(
                "delete from catalog.products where id = %s", (str(product_id),)
            )


async def all_product_hashes(conn=None) -> dict[str, str]:
    """{product_id: content_hash} for every product - the SQL side of reconcile()."""
    async with AsyncExitStack() as stack:
        c = await _conn_or_borrow(stack, conn)
        async with c.cursor() as cur:
            await cur.execute("select id, content_hash from catalog.products")
            rows = await cur.fetchall()
            return {str(r["id"]): r["content_hash"] for r in rows}


# --------------------------------------------------------------------------- #
# Events
# --------------------------------------------------------------------------- #


async def bulk_insert_events(
    user_id: UUID | str,
    session_id: UUID | str,
    events: Sequence[dict[str, Any]],
    conn=None,
) -> int:
    """One multi-row INSERT. ON CONFLICT DO NOTHING makes retried/duplicate
    beacons idempotent on `event_id` (ARCHITECTURE.md \u00a76.1/6.2)."""
    if not events:
        return 0
    async with AsyncExitStack() as stack:
        c = await _conn_or_borrow(stack, conn)
        async with c.cursor() as cur:
            rows = [
                (
                    e["event_id"],
                    str(user_id),
                    str(session_id),
                    e["type"],
                    e.get("product_id"),
                    Jsonb(e.get("payload", {})),
                    e["occurred_at"],
                )
                for e in events
            ]
            await cur.executemany(
                """
                insert into catalog.events
                    (event_id, user_id, session_id, type, product_id, payload, occurred_at)
                values (%s, %s, %s, %s, %s, %s, %s)
                on conflict (event_id) do nothing
                """,
                rows,
            )
            return cur.rowcount


async def recent_events(
    user_id: UUID | str, *, limit: int = 30, conn=None
) -> list[dict[str, Any]]:
    async with AsyncExitStack() as stack:
        c = await _conn_or_borrow(stack, conn)
        async with c.cursor() as cur:
            await cur.execute(
                """
                select * from catalog.events
                 where user_id = %s
                 order by occurred_at desc
                 limit %s
                """,
                (str(user_id), limit),
            )
            return await cur.fetchall()


async def recent_search_queries(
    user_id: UUID | str, *, limit: int = 10, conn=None
) -> list[str]:
    async with AsyncExitStack() as stack:
        c = await _conn_or_borrow(stack, conn)
        async with c.cursor() as cur:
            await cur.execute(
                """
                select payload->>'query' as query from catalog.events
                 where user_id = %s and type = 'search' and payload ? 'query'
                 order by occurred_at desc
                 limit %s
                """,
                (str(user_id), limit),
            )
            rows = await cur.fetchall()
            return [r["query"] for r in rows if r["query"]]


async def dismissed_and_owned_product_ids(user_id: UUID | str, conn=None) -> set[str]:
    async with AsyncExitStack() as stack:
        c = await _conn_or_borrow(stack, conn)
        async with c.cursor() as cur:
            await cur.execute(
                """
                select distinct product_id from catalog.events
                 where user_id = %s and type in ('dismiss', 'add_to_cart') and product_id is not null
                """,
                (str(user_id),),
            )
            rows = await cur.fetchall()
            return {str(r["product_id"]) for r in rows}


async def has_added_to_cart(
    user_id: UUID | str, product_id: UUID | str, conn=None
) -> bool:
    """Whether this user has an `add_to_cart` event for this specific product -
    drives the product page rendering the button as already-added on load."""
    async with AsyncExitStack() as stack:
        c = await _conn_or_borrow(stack, conn)
        async with c.cursor() as cur:
            await cur.execute(
                """
                select exists(
                    select 1 from catalog.events
                     where user_id = %s and product_id = %s and type = 'add_to_cart'
                ) as added
                """,
                (str(user_id), str(product_id)),
            )
            row = await cur.fetchone()
            return bool(row["added"]) if row else False


async def users_active_since(since: datetime, conn=None) -> list[str]:
    """Users with at least one event since `since` - the digest audience."""
    async with AsyncExitStack() as stack:
        c = await _conn_or_borrow(stack, conn)
        async with c.cursor() as cur:
            await cur.execute(
                "select distinct user_id from catalog.events where occurred_at >= %s",
                (since,),
            )
            rows = await cur.fetchall()
            return [str(r["user_id"]) for r in rows]


# --------------------------------------------------------------------------- #
# Digest queue (scheduled delivery, ARCHITECTURE.md \u00a710)
# --------------------------------------------------------------------------- #


async def enqueue_digest_users(user_ids: Sequence[str], conn=None) -> int:
    if not user_ids:
        return 0
    async with AsyncExitStack() as stack:
        c = await _conn_or_borrow(stack, conn)
        async with c.cursor() as cur:
            await cur.executemany(
                """
                insert into catalog.digest_queue (user_id)
                values (%s)
                on conflict (user_id) do update set status = 'pending', attempts = 0
                """,
                [(uid,) for uid in user_ids],
            )
            return len(user_ids)


async def claim_digest_queue(limit: int = 25, conn=None) -> list[dict[str, Any]]:
    async with AsyncExitStack() as stack:
        c = await _conn_or_borrow(stack, conn)
        async with c.cursor() as cur:
            await cur.execute(
                """
                select * from catalog.digest_queue
                 where status = 'pending'
                 order by enqueued_at
                 limit %s
                 for update skip locked
                """,
                (limit,),
            )
            return await cur.fetchall()


async def mark_digest_done(user_id: str, conn=None) -> None:
    async with AsyncExitStack() as stack:
        c = await _conn_or_borrow(stack, conn)
        async with c.cursor() as cur:
            await cur.execute(
                "update catalog.digest_queue set status = 'done' where user_id = %s",
                (user_id,),
            )


async def mark_digest_failed(user_id: str, conn=None) -> None:
    async with AsyncExitStack() as stack:
        c = await _conn_or_borrow(stack, conn)
        async with c.cursor() as cur:
            await cur.execute(
                "update catalog.digest_queue set status = 'failed', attempts = attempts + 1 where user_id = %s",
                (user_id,),
            )


# --------------------------------------------------------------------------- #
# Interest profile
# --------------------------------------------------------------------------- #


def _normalize_vector_columns(
    row: Optional[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    """`interest_vector`/`gen_vector` are pgvector columns; `register_vector_async`
    (db/pool.py) makes psycopg return them as numpy arrays, not lists. Every
    consumer of a profile row does plain Python truthiness (`if x`, `x or y`) on
    these fields, which raises `ValueError: truth value of an array...` on any
    array with more than one element. Normalizing once here, at the DB boundary,
    keeps every downstream call site free to use ordinary Python semantics."""
    if row is None:
        return None
    for key in ("interest_vector", "gen_vector"):
        value = row.get(key)
        if value is not None and not isinstance(value, list):
            row[key] = value.tolist()
    return row


async def get_profile(user_id: UUID | str, conn=None) -> Optional[dict[str, Any]]:
    async with AsyncExitStack() as stack:
        c = await _conn_or_borrow(stack, conn)
        async with c.cursor() as cur:
            await cur.execute(
                "select * from catalog.user_profiles where user_id = %s",
                (str(user_id),),
            )
            return _normalize_vector_columns(await cur.fetchone())


async def upsert_profile(
    user_id: UUID | str,
    *,
    weights: dict[str, float],
    interest_vector: Optional[list[float]],
    events_since_gen_delta: int = 0,
    profile_hash_value: Optional[str] = None,
    conn=None,
) -> dict[str, Any]:
    async with AsyncExitStack() as stack:
        c = await _conn_or_borrow(stack, conn)
        async with c.cursor() as cur:
            await cur.execute(
                """
                insert into catalog.user_profiles (user_id, weights, interest_vector, events_since_gen, profile_hash)
                values (%s, %s, %s, %s, %s)
                on conflict (user_id) do update
                   set weights = excluded.weights,
                       interest_vector = excluded.interest_vector,
                       events_since_gen = catalog.user_profiles.events_since_gen + %s,
                       profile_hash = excluded.profile_hash,
                       updated_at = now()
                returning *
                """,
                (
                    str(user_id),
                    Jsonb(weights),
                    interest_vector,
                    max(events_since_gen_delta, 0),
                    profile_hash_value,
                    events_since_gen_delta,
                ),
            )
            row = await cur.fetchone()
            assert row is not None, "insert ... returning * always yields one row"
            _normalize_vector_columns(row)
            return row


async def mark_generated(
    user_id: UUID | str,
    *,
    gen_vector: Optional[list[float]],
    profile_hash_value: str,
    conn=None,
) -> None:
    """Reset the drift baseline after a successful generation."""
    async with AsyncExitStack() as stack:
        c = await _conn_or_borrow(stack, conn)
        async with c.cursor() as cur:
            await cur.execute(
                """
                update catalog.user_profiles
                   set gen_vector = %s,
                       events_since_gen = 0,
                       last_generated_at = now()
                 where user_id = %s
                """,
                (gen_vector, str(user_id)),
            )
            _ = profile_hash_value  # profile_hash already carries current value; kept for signature clarity


# --------------------------------------------------------------------------- #
# Recommendations
# --------------------------------------------------------------------------- #


async def get_current_recommendation(
    user_id: UUID | str, conn=None
) -> Optional[dict[str, Any]]:
    async with AsyncExitStack() as stack:
        c = await _conn_or_borrow(stack, conn)
        async with c.cursor() as cur:
            await cur.execute(
                """
                select * from catalog.recommendations
                 where user_id = %s and is_current
                 limit 1
                """,
                (str(user_id),),
            )
            rec = await cur.fetchone()
            if not rec:
                return None
            await cur.execute(
                """
                select ri.*, p.title, p.description, p.category, p.level, p.price_cents
                  from catalog.recommendation_items ri
                  join catalog.products p on p.id = ri.product_id
                 where ri.rec_id = %s
                 order by ri.rank asc
                """,
                (rec["id"],),
            )
            rec["items"] = await cur.fetchall()
            return rec


async def persist_recommendation(
    *,
    user_id: UUID | str,
    narrative: str,
    trigger_reason: str,
    profile_hash_value: str,
    model: str,
    prompt_version: str,
    items: Sequence[dict[str, Any]],
    conn=None,
) -> dict[str, Any]:
    """Flip the previous current recommendation and insert the new one + items,
    all in one transaction (called with a transactional conn from persist node)."""
    async with AsyncExitStack() as stack:
        c = await _conn_or_borrow(stack, conn)
        async with c.cursor() as cur:
            await cur.execute(
                "update catalog.recommendations set is_current = false where user_id = %s and is_current",
                (str(user_id),),
            )
            await cur.execute(
                """
                insert into catalog.recommendations
                    (user_id, narrative, trigger_reason, profile_hash, model, prompt_version, is_current)
                values (%s, %s, %s, %s, %s, %s, true)
                returning *
                """,
                (
                    str(user_id),
                    narrative,
                    trigger_reason,
                    profile_hash_value,
                    model,
                    prompt_version,
                ),
            )
            rec = await cur.fetchone()
            for rank, item in enumerate(items, start=1):
                await cur.execute(
                    """
                    insert into catalog.recommendation_items (rec_id, product_id, rank, reason, score)
                    values (%s, %s, %s, %s, %s)
                    """,
                    (
                        rec["id"],
                        item["product_id"],
                        rank,
                        item["reason"],
                        item["score"],
                    ),
                )
            return rec


# --------------------------------------------------------------------------- #
# Agent runs (evidence trail for the trigger policy / cost claim)
# --------------------------------------------------------------------------- #


async def insert_agent_run(
    *,
    user_id: UUID | str,
    trigger_reason: str,
    cache_hit: bool = False,
    refine_loops: int = 0,
    retrieved_ids: Sequence[str] = (),
    node_timings: dict[str, Any] | None = None,
    model: Optional[str] = None,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
    error: Optional[str] = None,
    conn=None,
) -> dict[str, Any]:
    async with AsyncExitStack() as stack:
        c = await _conn_or_borrow(stack, conn)
        async with c.cursor() as cur:
            await cur.execute(
                """
                insert into catalog.agent_runs
                    (user_id, trigger_reason, cache_hit, refine_loops, retrieved_ids,
                     node_timings, model, prompt_tokens, completion_tokens, error)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                returning *
                """,
                (
                    str(user_id),
                    trigger_reason,
                    cache_hit,
                    refine_loops,
                    [str(i) for i in retrieved_ids],
                    Jsonb(node_timings or {}),
                    model,
                    prompt_tokens,
                    completion_tokens,
                    error,
                ),
            )
            return await cur.fetchone()


async def recent_agent_runs(limit: int = 50, conn=None) -> list[dict[str, Any]]:
    async with AsyncExitStack() as stack:
        c = await _conn_or_borrow(stack, conn)
        async with c.cursor() as cur:
            await cur.execute(
                "select * from catalog.agent_runs order by created_at desc limit %s",
                (limit,),
            )
            return await cur.fetchall()
