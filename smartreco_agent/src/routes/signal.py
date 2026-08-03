"""GET /api/live-signal - the read path behind the product page's live panel.

Polled every few seconds by `static/live-signal.js`. Purely a read of
already-computed state: recent events + the currently stored recommendation.
Never constructs a Mesh client, never calls `tracking.gate` or
`agent.graph.run_agent` - enforced by `tests/test_live_signal_no_llm.py`
(ARCHITECTURE.md \u00a76.1, \u00a715).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from smartreco_agent.src.auth.dependencies import CurrentUser, require_user
from smartreco_agent.src.db import catalog
from smartreco_agent.src.schema import (
    LiveSignalResponse,
    SignalRecommendation,
    SignalRecommendationItem,
)
from smartreco_agent.src.tracking.signal_feed import humanize_events

router = APIRouter()

FEED_LIMIT = 8


def _serialize_recommendation(
    rec: dict | None,
) -> SignalRecommendation | None:
    if rec is None:
        return None
    return SignalRecommendation(
        narrative=rec["narrative"],
        items=[
            SignalRecommendationItem(
                product_id=str(item["product_id"]),
                title=item["title"],
                category=item["category"],
                price_cents=item["price_cents"],
                reason=item["reason"],
            )
            for item in rec.get("items", [])[:2]
        ],
    )


@router.get("/api/live-signal", response_model=LiveSignalResponse)
async def live_signal(
    user: CurrentUser = Depends(require_user),
) -> LiveSignalResponse:
    events = await catalog.recent_events(user.id, limit=FEED_LIMIT)

    product_ids = {str(e["product_id"]) for e in events if e.get("product_id")}
    products_by_id = (
        {str(p["id"]): p for p in await catalog.get_products_by_ids(list(product_ids))}
        if product_ids
        else {}
    )

    feed = humanize_events(events, products_by_id)
    rec = await catalog.get_current_recommendation(user.id)

    return LiveSignalResponse(feed=feed, recommendation=_serialize_recommendation(rec))
