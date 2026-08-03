"""test_outbox_skips_unchanged_content (ARCHITECTURE.md \u00a715, evidence item #5).

`content_hash` only covers the fields that are actually embedded (title,
description, category, level, tags) - editing `price_cents` must not change
it, so `drain_outbox` skips the embedding call entirely for a price-only
edit. Verified at two levels: the pure hash function, and the drainer
deciding not to call `embed_products` when the stored hash already matches.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from smartreco_agent.src.cron import outbox_drainer
from smartreco_agent.src.db.hashing import content_hash

PRODUCT_ID = "cccccccc-0000-0000-0000-000000000001"


def test_content_hash_ignores_price():
    base = dict(
        title="Agentic AI Foundations",
        description="Learn what makes an AI system agentic.",
        category="Agentic AI",
        level="beginner",
        tags=["langgraph", "agents"],
    )
    assert content_hash(**base) == content_hash(**base)  # sanity: deterministic

    # price_cents is not a parameter of content_hash at all - editing it in the
    # DB can never change the hash, by construction. This asserts the embeddable
    # fields alone determine the hash regardless of tag ordering.
    reordered = {**base, "tags": list(reversed(base["tags"]))}
    assert content_hash(**base) == content_hash(**reordered)

    changed_title = {**base, "title": "Agentic AI Foundations!!"}
    assert content_hash(**base) != content_hash(**changed_title)


@pytest.mark.asyncio
async def test_drain_outbox_skips_unchanged_content(monkeypatch):
    unchanged_hash = "same-hash"
    product = {
        "id": PRODUCT_ID,
        "title": "Agentic AI Foundations",
        "description": "...",
        "category": "Agentic AI",
        "level": "beginner",
        "tags": ["langgraph"],
        "price_cents": 9900,  # bumped from 4900 - a price-only edit
        "is_active": True,
        "content_hash": unchanged_hash,
    }
    outbox_row = {"id": 1, "product_id": PRODUCT_ID, "op": "upsert"}

    monkeypatch.setattr(outbox_drainer.outbox, "claim_pending", AsyncMock(return_value=[outbox_row]))
    monkeypatch.setattr(outbox_drainer.catalog, "get_products_by_ids", AsyncMock(return_value=[product]))
    mark_done = AsyncMock()
    monkeypatch.setattr(outbox_drainer.outbox, "mark_done", mark_done)
    monkeypatch.setattr(outbox_drainer.outbox, "mark_failed", AsyncMock())

    embed_products = AsyncMock()
    monkeypatch.setattr(outbox_drainer, "embed_products", embed_products)

    fake_store = AsyncMock()
    fake_store.all_hashes = AsyncMock(return_value={PRODUCT_ID: unchanged_hash})
    monkeypatch.setattr(outbox_drainer, "get_vector_store", lambda: fake_store)

    report = await outbox_drainer.drain_outbox()

    embed_products.assert_not_called()
    fake_store.upsert.assert_not_called()
    mark_done.assert_awaited_once_with(outbox_row["id"])
    assert report.skipped_unchanged == 1
    assert report.embedded == 0


@pytest.mark.asyncio
async def test_drain_outbox_embeds_when_content_actually_changed(monkeypatch):
    product = {
        "id": PRODUCT_ID,
        "title": "Agentic AI Foundations (rewritten)",
        "description": "...",
        "category": "Agentic AI",
        "level": "beginner",
        "tags": ["langgraph"],
        "price_cents": 9900,
        "is_active": True,
        "content_hash": "new-hash",
    }
    outbox_row = {"id": 2, "product_id": PRODUCT_ID, "op": "upsert"}

    monkeypatch.setattr(outbox_drainer.outbox, "claim_pending", AsyncMock(return_value=[outbox_row]))
    monkeypatch.setattr(outbox_drainer.catalog, "get_products_by_ids", AsyncMock(return_value=[product]))
    mark_done = AsyncMock()
    monkeypatch.setattr(outbox_drainer.outbox, "mark_done", mark_done)
    monkeypatch.setattr(outbox_drainer.outbox, "mark_failed", AsyncMock())

    from smartreco_agent.src.vectors.protocol import EmbeddedProduct

    embedded = [
        EmbeddedProduct(
            product_id=PRODUCT_ID, embedding=[0.1, 0.2], content_hash="new-hash",
            model="test-model", category="Agentic AI", level="beginner", price_cents=9900,
        )
    ]
    embed_products = AsyncMock(return_value=embedded)
    monkeypatch.setattr(outbox_drainer, "embed_products", embed_products)

    fake_store = AsyncMock()
    fake_store.all_hashes = AsyncMock(return_value={PRODUCT_ID: "old-hash"})
    monkeypatch.setattr(outbox_drainer, "get_vector_store", lambda: fake_store)

    report = await outbox_drainer.drain_outbox()

    embed_products.assert_awaited_once_with([product])
    fake_store.upsert.assert_awaited_once_with(embedded)
    mark_done.assert_awaited_once_with(outbox_row["id"])
    assert report.embedded == 1
    assert report.skipped_unchanged == 0
