"""Enqueue step of the daily digest: one cheap statement, returns fast.

Split into enqueue + drain (`worker.py`) because a single serverless
invocation cannot fan out to N users inside the duration cap
(ARCHITECTURE.md \u00a710)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from smartreco_agent.src.db import catalog


async def enqueue_digest(lookback_hours: int = 24) -> int:
    since = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    user_ids = await catalog.users_active_since(since)
    return await catalog.enqueue_digest_users(user_ids)
