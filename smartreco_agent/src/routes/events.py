"""POST /api/events - the ingest path.

One round trip, one multi-row INSERT, `202` returned before any interest-model
work happens. Nothing on the response path constructs a Mesh client - enforced
by `tests/test_no_llm_in_ingest.py` which patches the client constructor to
raise and asserts the endpoint still returns 202 (ARCHITECTURE.md \u00a76.2, \u00a715).
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, status

from smartreco_agent.src.agent.graph import run_agent
from smartreco_agent.src.auth.dependencies import CurrentUser, require_user
from smartreco_agent.src.db import catalog
from smartreco_agent.src.schema import EventBatch, IngestResponse
from smartreco_agent.src.settings import settings
from smartreco_agent.src.tracking import gate, profile
from smartreco_agent.utils.pylogger import get_python_logger

router = APIRouter()
logger = get_python_logger(settings.PYTHON_LOG_LEVEL)


async def _process_batch_and_maybe_generate(user_id: str, events: list[dict]) -> None:
    """Runs entirely in a BackgroundTask, after the 202 has already gone out."""
    try:
        await profile.apply(user_id, events)
        reason = await gate.should_generate(user_id)
        if reason:
            logger.info("trigger_fired", user_id=user_id, reason=reason)
            await run_agent(user_id, trigger_reason=reason)
    except Exception as e:  # noqa: BLE001 - background work must never crash the process
        logger.error("event_processing_failed", user_id=user_id, error=str(e), exc_info=True)


@router.post("/api/events", status_code=status.HTTP_202_ACCEPTED, response_model=IngestResponse)
async def ingest(
    batch: EventBatch,
    background_tasks: BackgroundTasks,
    user: CurrentUser = Depends(require_user),
) -> IngestResponse:
    events_payload = [
        {
            "event_id": str(e.event_id),
            "type": e.type,
            "product_id": str(e.product_id) if e.product_id else None,
            "payload": e.payload,
            "occurred_at": e.occurred_at,
        }
        for e in batch.events
    ]

    inserted = await catalog.bulk_insert_events(user.id, str(batch.session_id), events_payload)
    background_tasks.add_task(_process_batch_and_maybe_generate, user.id, events_payload)

    return IngestResponse(accepted=inserted)
