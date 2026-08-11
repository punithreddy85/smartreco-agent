"""GET /api/live-signal is a pure read of already-computed state, polled every
few seconds by the product page. Patches the Mesh client constructor to
raise and asserts the endpoint still returns 200 *and* the Mesh client was
never constructed - proving the live panel can never trigger agent
generation or otherwise touch the LLM/embedding gateway
(ARCHITECTURE.md \u00a76.1, \u00a715)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from smartreco_agent.src.api import app
from smartreco_agent.src.auth.dependencies import CurrentUser, require_user
from smartreco_agent.src.db import catalog
from smartreco_agent.src.mesh import client as mesh_client

TEST_USER = CurrentUser(id="33333333-3333-3333-3333-333333333333", role="user")

PRODUCT_ID = "44444444-4444-4444-4444-444444444444"

NOW = datetime.now(timezone.utc)


@pytest.fixture
def client(monkeypatch):
    def _raise(*_a, **_kw):
        raise AssertionError("Mesh client must never be constructed on the signal path")

    monkeypatch.setattr(mesh_client, "get_mesh_client", MagicMock(side_effect=_raise))
    monkeypatch.setattr(
        catalog,
        "recent_events",
        AsyncMock(
            return_value=[
                {
                    "type": "product_view",
                    "product_id": PRODUCT_ID,
                    "payload": {},
                    "occurred_at": NOW,
                },
            ]
        ),
    )
    monkeypatch.setattr(
        catalog,
        "get_products_by_ids",
        AsyncMock(
            return_value=[
                {
                    "id": PRODUCT_ID,
                    "title": "Tool-Calling and Function Execution for Agents",
                    "category": "Agentic AI",
                }
            ]
        ),
    )
    monkeypatch.setattr(
        catalog,
        "get_current_recommendation",
        AsyncMock(
            return_value={
                "narrative": "You keep circling agentic AI.",
                "trigger_reason": "drift",
                "created_at": NOW,
                "items": [
                    {
                        "product_id": PRODUCT_ID,
                        "title": "Tool-Calling and Function Execution for Agents",
                        "category": "Agentic AI",
                        "price_cents": 8900,
                        "reason": "Matches your recent browsing.",
                    }
                ],
            }
        ),
    )
    monkeypatch.setattr(
        catalog,
        "get_profile",
        AsyncMock(
            return_value={
                "events_since_gen": 2,
                "weights": {"category:Agentic AI": 0.8, "category:Security": 0.2},
            }
        ),
    )

    # Deliberately not using `with TestClient(app)` - that would run the real
    # lifespan (`open_pool()`), which tries to reach an actual Postgres.
    app.dependency_overrides[require_user] = lambda: TEST_USER
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


def test_live_signal_returns_200_without_constructing_mesh_client(client):
    response = client.get("/api/live-signal")

    assert response.status_code == 200
    mesh_client.get_mesh_client.assert_not_called()

    body = response.json()
    assert body["feed"] == [
        {
            "label": "Viewed",
            "detail": "Tool-Calling and Function Execution for Agents",
            "icon": "eye",
            "is_latest": True,
            "occurred_at": "now",
        }
    ]
    assert body["recommendation"]["narrative"] == "You keep circling agentic AI."
    assert body["recommendation"]["trigger_reason"] == "drift"
    assert body["recommendation"]["refreshed_at"] == "now"
    assert len(body["recommendation"]["items"]) == 1
    assert body["events_since_gen"] == 2
    assert body["trigger_threshold"] == 3
    assert body["top_interests"] == [
        {"label": "Agentic AI", "pct": 80},
        {"label": "Security", "pct": 20},
    ]


def test_live_signal_handles_no_recommendation_yet(client, monkeypatch):
    monkeypatch.setattr(
        catalog, "get_current_recommendation", AsyncMock(return_value=None)
    )

    response = client.get("/api/live-signal")

    assert response.status_code == 200
    assert response.json()["recommendation"] is None


def test_events_since_gen_is_clamped_to_the_trigger_threshold(client, monkeypatch):
    """Regression test: `gate.should_generate` checks the cooldown and
    unchanged-profile-hash bailouts before the count check, so a burst of
    events landing inside the cooldown window can push the stored counter
    past the threshold (e.g. 14 with a threshold of 3) before a trigger ever
    gets a chance to fire. That's harmless for the trigger logic itself, but
    "progress toward next refresh" is a bounded metric and must never report
    past its own threshold - like a token-bucket counter capped at capacity."""
    monkeypatch.setattr(
        catalog,
        "get_profile",
        AsyncMock(
            return_value={
                "events_since_gen": 14,
                "weights": {},
            }
        ),
    )

    response = client.get("/api/live-signal")

    body = response.json()
    assert body["events_since_gen"] == 3
    assert body["trigger_threshold"] == 3
