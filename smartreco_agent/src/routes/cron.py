"""Cron-triggered endpoints. Publicly addressable, so every one of them is
gated on a constant-time secret comparison (ARCHITECTURE.md \u00a710, \u00a713).

In production these are invoked by `pg_cron` + `pg_net` on the schedule in
Appendix B.5. Locally (no `pg_cron`), the Makefile drives the same endpoints
by hand - see \u00a712.3.
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Header, HTTPException, status

from smartreco_agent.src.cron.digest import enqueue_digest
from smartreco_agent.src.cron.outbox_drainer import drain_outbox
from smartreco_agent.src.cron.reconcile import reconcile
from smartreco_agent.src.cron.worker import run_digest_worker
from smartreco_agent.src.settings import settings

router = APIRouter(prefix="/api/cron")


def _check_secret(x_cron_secret: str | None) -> None:
    if not x_cron_secret or not hmac.compare_digest(x_cron_secret, settings.CRON_SECRET):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid cron secret")


@router.post("/digest")
async def cron_digest(x_cron_secret: str | None = Header(default=None)):
    _check_secret(x_cron_secret)
    enqueued = await enqueue_digest()
    return {"enqueued": enqueued}


@router.post("/digest-worker")
async def cron_digest_worker(x_cron_secret: str | None = Header(default=None)):
    _check_secret(x_cron_secret)
    report = await run_digest_worker()
    return {"processed": report.processed, "sent": report.sent, "failed": report.failed}


@router.post("/outbox")
async def cron_outbox(x_cron_secret: str | None = Header(default=None)):
    _check_secret(x_cron_secret)
    report = await drain_outbox()
    return {
        "claimed": report.claimed, "embedded": report.embedded,
        "skipped_unchanged": report.skipped_unchanged, "deleted": report.deleted, "failed": report.failed,
    }


@router.post("/reconcile")
async def cron_reconcile(x_cron_secret: str | None = Header(default=None)):
    _check_secret(x_cron_secret)
    report = await reconcile()
    return {"missing": report.missing, "stale": report.stale, "orphans": report.orphans}
