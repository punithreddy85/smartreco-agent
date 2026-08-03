"""Async connection pool for the `catalog` and `vectors` schemas.

One pool for the whole process, lazily created and reused across warm
invocations (matters on Vercel cold starts). Against the Supabase transaction
pooler (port 6543) prepared statements are not supported, so
`DB_DISABLE_PREPARE=true` must be set in that environment - the pool reads a
single flag rather than branching on environment name, so the difference
between prod and local is one variable, not two code paths (ARCHITECTURE.md \u00a712.3).

Supavisor (the transaction pooler) also closes connections that sit idle for
too long. `max_idle` proactively recycles them before that happens, and
`check` validates a pooled connection right before handing it to a request -
without both, a request can be handed a connection Supavisor already killed
server-side, surfacing as a raw socket error instead of a clean reconnect.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from pgvector.psycopg import register_vector_async
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from smartreco_agent.src.settings import settings
from smartreco_agent.utils.pylogger import get_python_logger

logger = get_python_logger(settings.PYTHON_LOG_LEVEL)

_pool: AsyncConnectionPool | None = None


async def _configure_connection(conn) -> None:
    """Per-connection setup: dict rows and pgvector adapters."""
    conn.row_factory = dict_row
    await register_vector_async(conn)


def get_pool() -> AsyncConnectionPool:
    """Return the process-wide connection pool, creating it on first use."""
    global _pool
    if _pool is None:
        kwargs = {"prepare_threshold": None} if settings.DB_DISABLE_PREPARE else {}
        _pool = AsyncConnectionPool(
            conninfo=settings.DATABASE_URL,
            min_size=settings.DB_POOL_MIN_SIZE,
            max_size=settings.DB_POOL_MAX_SIZE,
            kwargs=kwargs,
            configure=_configure_connection,
            check=AsyncConnectionPool.check_connection,
            max_idle=120,
            open=False,
        )
        logger.info(
            "Created Postgres connection pool",
            disable_prepare=settings.DB_DISABLE_PREPARE,
            max_size=settings.DB_POOL_MAX_SIZE,
        )
    return _pool


async def open_pool() -> None:
    """Open the pool. Call once from the application lifespan."""
    pool = get_pool()
    if pool.closed:
        await pool.open(wait=True, timeout=15)


async def close_pool() -> None:
    """Close the pool. Call once from the application lifespan shutdown."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def get_connection() -> AsyncIterator:
    """Borrow a single connection from the pool (auto-returned on exit)."""
    pool = get_pool()
    async with pool.connection() as conn:
        yield conn


@asynccontextmanager
async def transaction() -> AsyncIterator:
    """Borrow a connection and open an explicit transaction block.

    Used wherever two writes must be atomic - most importantly the admin
    product write plus its outbox row (ARCHITECTURE.md \u00a75.2).
    """
    pool = get_pool()
    async with pool.connection() as conn:
        async with conn.transaction():
            yield conn
