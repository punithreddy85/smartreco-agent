"""test_no_llm_in_ingest_path (ARCHITECTURE.md \u00a715, evidence item #2).

Patches the Mesh client constructor to raise, POSTs an event batch, and
asserts the endpoint still returns 202 *and* that the Mesh client was never
constructed - proving nothing on the ingest response path (or the
BackgroundTask it schedules, for a batch with no product/search signal and an
unchanged profile hash) ever touches the LLM/embedding gateway.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from smartreco_agent.src.api import app
from smartreco_agent.src.auth.dependencies import CurrentUser, require_user
from smartreco_agent.src.db import catalog
from smartreco_agent.src.mesh import client as mesh_client

TEST_USER = CurrentUser(id="22222222-2222-2222-2222-222222222222", role="user")


@pytest.fixture
def client(monkeypatch):
    def _raise(*_a, **_kw):
        raise AssertionError("Mesh client must never be constructed on the ingest path")

    monkeypatch.setattr(mesh_client, "get_mesh_client", MagicMock(side_effect=_raise))
    monkeypatch.setattr(catalog, "bulk_insert_events", AsyncMock(return_value=2))
    monkeypatch.setattr(catalog, "get_profile", AsyncMock(return_value={"weights": {}, "updated_at": None}))
    monkeypatch.setattr(catalog, "get_products_by_ids", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        catalog,
        "upsert_profile",
        AsyncMock(
            return_value={
                "user_id": TEST_USER.id,
                "weights": {},
                "interest_vector": None,
                "events_since_gen": 1,
                "last_generated_at": None,
                "profile_hash": "unchanged",
            }
        ),
    )
    monkeypatch.setattr(
        catalog, "get_current_recommendation", AsyncMock(return_value={"profile_hash": "unchanged", "items": []})
    )

    # Deliberately not using `with TestClient(app)` - that would run the real
    # lifespan (`open_pool()`), which tries to reach an actual Postgres. This
    # test only needs the ASGI app's request handling, not its lifespan.
    app.dependency_overrides[require_user] = lambda: TEST_USER
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


def _batch(n: int = 2) -> dict:
    return {
        "session_id": str(uuid.uuid4()),
        "events": [
            {
                "event_id": str(uuid.uuid4()),
                "type": "click",
                "product_id": None,
                "payload": {},
                "occurred_at": datetime.now(timezone.utc).isoformat(),
            }
            for _ in range(n)
        ],
    }


def test_ingest_returns_202_without_constructing_mesh_client(client):
    response = client.post("/api/events", json=_batch())

    assert response.status_code == 202
    assert response.json() == {"accepted": 2}
    mesh_client.get_mesh_client.assert_not_called()


def test_ingest_rejects_empty_batch(client):
    response = client.post("/api/events", json={"session_id": str(uuid.uuid4()), "events": []})

    assert response.status_code == 422  # EventBatch requires min_length=1


def test_ingest_rejects_oversized_batch(client):
    response = client.post("/api/events", json=_batch(51))

    assert response.status_code == 422  # EventBatch caps at max_length=50
