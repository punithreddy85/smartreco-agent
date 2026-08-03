"""Hash-diff reconciliation between `catalog.products` and `vectors.product_embeddings`.

The piece that makes "kept in sync" demonstrable rather than asserted
(ARCHITECTURE.md \u00a75.4): it never trusts the outbox alone, it diffs the two
stores directly and re-enqueues whatever has drifted.
"""

from __future__ import annotations

from dataclasses import dataclass

from smartreco_agent.src.db import catalog, outbox
from smartreco_agent.src.vectors.pgvector_store import get_vector_store


@dataclass
class ReconcileReport:
    missing: int
    stale: int
    orphans: int


async def reconcile() -> ReconcileReport:
    store = get_vector_store()
    sql_hashes = await catalog.all_product_hashes()
    vec_hashes = await store.all_hashes()

    missing = sql_hashes.keys() - vec_hashes.keys()          # never embedded
    stale = {k for k in sql_hashes.keys() & vec_hashes.keys() if sql_hashes[k] != vec_hashes[k]}
    orphans = vec_hashes.keys() - sql_hashes.keys()           # deleted, not purged

    await outbox.enqueue_many(list(missing | stale), op="upsert")
    await outbox.enqueue_many(list(orphans), op="delete")

    return ReconcileReport(missing=len(missing), stale=len(stale), orphans=len(orphans))
