"""Digest drain step: claims a chunk of `digest_queue`, runs the agent (or
reuses a cached recommendation), sends the email, and stops at a hard time
budget - leaving the remainder for the next `pg_cron` tick (ARCHITECTURE.md \u00a710)."""

from __future__ import annotations

import time
from dataclasses import dataclass

from smartreco_agent.src.agent.graph import run_agent
from smartreco_agent.src.cron.email import send_digest_email
from smartreco_agent.src.db import catalog
from smartreco_agent.src.settings import settings
from smartreco_agent.utils.pylogger import get_python_logger

logger = get_python_logger(settings.PYTHON_LOG_LEVEL)

TIME_BUDGET_SECONDS = 45


@dataclass
class DigestReport:
    processed: int = 0
    sent: int = 0
    failed: int = 0


async def run_digest_worker(limit: int = 25) -> DigestReport:
    report = DigestReport()
    deadline = time.monotonic() + TIME_BUDGET_SECONDS

    rows = await catalog.claim_digest_queue(limit=limit)
    for row in rows:
        if time.monotonic() >= deadline:
            logger.info("digest_worker_time_budget_reached", processed=report.processed)
            break

        user_id = str(row["user_id"])
        try:
            rec = await run_agent(user_id, trigger_reason="scheduled")
            if not rec:
                await catalog.mark_digest_done(user_id)
                report.processed += 1
                continue

            user = await catalog.get_user_by_id(user_id)
            if user:
                sent = await send_digest_email(
                    to_email=user["email"],
                    narrative=rec["narrative"],
                    items=rec.get("items", []),
                )
                report.sent += int(sent)
            await catalog.mark_digest_done(user_id)
            report.processed += 1
        except Exception as e:  # noqa: BLE001 - one bad user must not stall the whole batch
            logger.error("digest_worker_user_failed", user_id=user_id, error=str(e))
            await catalog.mark_digest_failed(user_id)
            report.failed += 1

    return report
