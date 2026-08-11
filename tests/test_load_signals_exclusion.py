"""P0.1 regression: `load_signals` must exclude the product the user is
currently viewing (and, on a `count` trigger, the products already in the
current recommendation) from `excluded_product_ids` - otherwise `retrieve`
can hand the agent its own current page as a "recommendation" (ARCHITECTURE.md
\u00a79.3). No DB, no LLM: `catalog` is fully monkeypatched."""

from __future__ import annotations

from unittest.mock import AsyncMock

from smartreco_agent.src.agent.nodes import load_signals as load_signals_module
from smartreco_agent.src.agent.nodes.load_signals import load_signals

CURRENT_PRODUCT_ID = "11111111-1111-1111-1111-111111111111"
OTHER_PRODUCT_ID = "22222222-2222-2222-2222-222222222222"
DISMISSED_PRODUCT_ID = "33333333-3333-3333-3333-333333333333"


def _patch_catalog(
    monkeypatch,
    *,
    recent_events=None,
    dismissed_and_owned=None,
    current_rec_items=None,
):
    catalog = load_signals_module.catalog
    monkeypatch.setattr(catalog, "get_profile", AsyncMock(return_value={}))
    monkeypatch.setattr(
        catalog, "recent_events", AsyncMock(return_value=recent_events or [])
    )
    monkeypatch.setattr(catalog, "recent_search_queries", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        catalog,
        "dismissed_and_owned_product_ids",
        AsyncMock(return_value=dismissed_and_owned or set()),
    )
    monkeypatch.setattr(
        catalog,
        "current_recommendation_product_ids",
        AsyncMock(return_value=current_rec_items or set()),
    )


async def test_currently_viewed_product_is_excluded(monkeypatch):
    _patch_catalog(
        monkeypatch,
        recent_events=[
            {"type": "product_view", "product_id": CURRENT_PRODUCT_ID, "payload": {}},
        ],
        dismissed_and_owned={DISMISSED_PRODUCT_ID},
    )

    result = await load_signals({"user_id": "u1", "trigger_reason": "drift"})

    assert result["current_product_id"] == CURRENT_PRODUCT_ID
    assert result["excluded_product_ids"] == {CURRENT_PRODUCT_ID, DISMISSED_PRODUCT_ID}


async def test_most_recent_product_view_wins_when_several_are_present(monkeypatch):
    _patch_catalog(
        monkeypatch,
        recent_events=[
            {"type": "product_view", "product_id": CURRENT_PRODUCT_ID, "payload": {}},
            {"type": "click", "product_id": OTHER_PRODUCT_ID, "payload": {}},
            {"type": "product_view", "product_id": OTHER_PRODUCT_ID, "payload": {}},
        ],
    )

    result = await load_signals({"user_id": "u1", "trigger_reason": "drift"})

    assert result["current_product_id"] == CURRENT_PRODUCT_ID


async def test_no_product_view_leaves_current_product_id_none(monkeypatch):
    _patch_catalog(
        monkeypatch,
        recent_events=[{"type": "search", "product_id": None, "payload": {}}],
    )

    result = await load_signals({"user_id": "u1", "trigger_reason": "drift"})

    assert result["current_product_id"] is None
    assert result["excluded_product_ids"] == set()


async def test_count_trigger_also_excludes_current_recommendation_items(monkeypatch):
    _patch_catalog(
        monkeypatch,
        recent_events=[],
        current_rec_items={OTHER_PRODUCT_ID},
    )

    result = await load_signals({"user_id": "u1", "trigger_reason": "count"})

    assert result["excluded_product_ids"] == {OTHER_PRODUCT_ID}
    load_signals_module.catalog.current_recommendation_product_ids.assert_awaited_once_with(
        "u1"
    )


async def test_drift_trigger_does_not_exclude_current_recommendation_items(monkeypatch):
    _patch_catalog(
        monkeypatch,
        recent_events=[],
        current_rec_items={OTHER_PRODUCT_ID},
    )

    result = await load_signals({"user_id": "u1", "trigger_reason": "drift"})

    assert result["excluded_product_ids"] == set()
    load_signals_module.catalog.current_recommendation_product_ids.assert_not_awaited()
