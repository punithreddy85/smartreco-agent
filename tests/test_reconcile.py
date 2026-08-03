"""test_reconcile_repairs_drift (ARCHITECTURE.md \u00a715, evidence item #3).

Simulates a vector-store row that has drifted from `catalog.products` (one
missing entirely, one with a stale hash, one orphaned in the vector store
after its product row was deleted) and asserts `reconcile()` classifies and
re-enqueues each case correctly - without needing a live database, by
monkeypatching the catalog/outbox/vector-store seams `reconcile()` calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from smartreco_agent.src.cron import reconcile as reconcile_module

PID_MISSING = "aaaaaaaa-0000-0000-0000-000000000001"  # in SQL, never embedded
PID_STALE = "aaaaaaaa-0000-0000-0000-000000000002"  # in both, hash differs
PID_SYNCED = "aaaaaaaa-0000-0000-0000-000000000003"  # in both, hash matches - untouched
PID_ORPHAN = "aaaaaaaa-0000-0000-0000-000000000004"  # in vectors only - product row deleted


@pytest.mark.asyncio
async def test_reconcile_repairs_drift(monkeypatch):
    sql_hashes = {
        PID_MISSING: "hash-missing",
        PID_STALE: "hash-stale-new",
        PID_SYNCED: "hash-synced",
    }
    vec_hashes = {
        PID_STALE: "hash-stale-old",
        PID_SYNCED: "hash-synced",
        PID_ORPHAN: "hash-orphan",
    }

    monkeypatch.setattr(reconcile_module.catalog, "all_product_hashes", AsyncMock(return_value=sql_hashes))

    fake_store = AsyncMock()
    fake_store.all_hashes = AsyncMock(return_value=vec_hashes)
    monkeypatch.setattr(reconcile_module, "get_vector_store", lambda: fake_store)

    enqueue_many = AsyncMock(side_effect=lambda ids, op: len(ids))
    monkeypatch.setattr(reconcile_module.outbox, "enqueue_many", enqueue_many)

    report = await reconcile_module.reconcile()

    assert report.missing == 1
    assert report.stale == 1
    assert report.orphans == 1

    upsert_call = next(c for c in enqueue_many.call_args_list if c.kwargs.get("op") == "upsert")
    delete_call = next(c for c in enqueue_many.call_args_list if c.kwargs.get("op") == "delete")

    assert set(upsert_call.args[0]) == {PID_MISSING, PID_STALE}
    assert set(delete_call.args[0]) == {PID_ORPHAN}
    # The in-sync product must never be re-enqueued in either direction.
    assert PID_SYNCED not in upsert_call.args[0]
    assert PID_SYNCED not in delete_call.args[0]
