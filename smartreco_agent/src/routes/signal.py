"""GET /api/live-signal - the read path behind the product page's live panel.

Polled every few seconds by `static/live-signal.js`. Purely a read of
already-computed state: recent events + the currently stored recommendation.
Never constructs a Mesh client, never calls `tracking.gate` or
`agent.graph.run_agent` - enforced by `tests/test_live_signal_no_llm.py`
(ARCHITECTURE.md \u00a76.1, \u00a715).
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from smartreco_agent.src.auth.dependencies import CurrentUser, require_user
from smartreco_agent.src.db import catalog
from smartreco_agent.src.schema import (
    InterestWeight,
    LiveSignalResponse,
    SignalRecommendation,
    SignalRecommendationItem,
)
from smartreco_agent.src.settings import settings
from smartreco_agent.src.tracking.signal_feed import (
    humanize_events,
    relative_time,
    top_interests,
)

router = APIRouter()

FEED_LIMIT = 8


def _serialize_recommendation(
    rec: dict | None, *, now: datetime
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
        trigger_reason=rec.get("trigger_reason"),
        refreshed_at=relative_time(rec["created_at"], now)
        if rec.get("created_at")
        else None,
    )


@router.get("/api/live-signal", response_model=LiveSignalResponse)
async def live_signal(
    user: CurrentUser = Depends(require_user),
) -> LiveSignalResponse:
    now = datetime.now(timezone.utc)
    events = await catalog.recent_events(user.id, limit=FEED_LIMIT)

    product_ids = {str(e["product_id"]) for e in events if e.get("product_id")}
    products_by_id = (
        {str(p["id"]): p for p in await catalog.get_products_by_ids(list(product_ids))}
        if product_ids
        else {}
    )

    feed = humanize_events(events, products_by_id, now=now)
    rec = await catalog.get_current_recommendation(user.id)
    profile = await catalog.get_profile(user.id)

    trigger_threshold = settings.TRIGGER_COUNT_THRESHOLD
    raw_events_since_gen = (profile or {}).get("events_since_gen", 0)
    # `events_since_gen` can outrun the threshold in storage: `gate.should_generate`
    # checks the cooldown and unchanged-profile-hash bailouts *before* the count
    # check, so a burst of events landing inside the cooldown window keeps
    # incrementing with no chance to act on it. This is harmless for the trigger
    # logic itself (`>=` still fires once the cooldown clears) but "progress
    # toward next refresh" is a bounded metric - clamp it at the API boundary,
    # the same way a token-bucket counter never reports past its capacity.
    events_since_gen = min(raw_events_since_gen, trigger_threshold)

    return LiveSignalResponse(
        feed=feed,
        recommendation=_serialize_recommendation(rec, now=now),
        events_since_gen=events_since_gen,
        trigger_threshold=trigger_threshold,
        top_interests=[
            InterestWeight(**w) for w in top_interests((profile or {}).get("weights"))
        ],
    )
