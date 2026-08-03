"""Drains `catalog.vector_outbox` into `vectors.product_embeddings`.

Runs as a FastAPI BackgroundTask immediately after an admin write (fast path)
and from a `pg_cron` sweep every five minutes (safety net). Hash-skipping means
a price-only edit costs zero embedding calls - the property `test_outbox_skips_unchanged_content`
in `tests/` asserts directly (ARCHITECTURE.md \u00a75.3).
"""

from __future__ import annotations

from dataclasses import dataclass

from smartreco_agent.src.db import catalog, outbox
from smartreco_agent.src.settings import settings
from smartreco_agent.src.vectors.embedder import embed_products
from smartreco_agent.src.vectors.pgvector_store import get_vector_store
from smartreco_agent.utils.pylogger import get_python_logger

logger = get_python_logger(settings.PYTHON_LOG_LEVEL)


@dataclass
class DrainReport:
    claimed: int = 0
    embedded: int = 0
    skipped_unchanged: int = 0
    deleted: int = 0
    failed: int = 0


async def drain_outbox(limit: int = 50) -> DrainReport:
    report = DrainReport()
    store = get_vector_store()

    rows = await outbox.claim_pending(limit=limit)
    report.claimed = len(rows)
    if not rows:
        return report

    delete_rows = [r for r in rows if r["op"] == "delete"]
    upsert_rows = [r for r in rows if r["op"] == "upsert"]

    if delete_rows:
        ids = [str(r["product_id"]) for r in delete_rows]
        try:
            await store.delete(ids)
            for r in delete_rows:
                await outbox.mark_done(r["id"])
            report.deleted += len(delete_rows)
        except Exception as e:  # noqa: BLE001 - outbox rows must not be lost on failure
            logger.error("outbox_delete_failed", error=str(e))
            for r in delete_rows:
                await outbox.mark_failed(r["id"], str(e))
            report.failed += len(delete_rows)

    if upsert_rows:
        product_ids = [str(r["product_id"]) for r in upsert_rows]
        products = {str(p["id"]): p for p in await catalog.get_products_by_ids(product_ids)}
        existing_hashes = await store.all_hashes()

        needs_embed: list[dict] = []
        needs_embed_outbox_ids: list[int] = []

        for row in upsert_rows:
            pid = str(row["product_id"])
            product = products.get(pid)

            if product is None:
                # Deleted after enqueue - converge to a delete instead of failing.
                try:
                    await store.delete([pid])
                    await outbox.mark_done(row["id"])
                    report.deleted += 1
                except Exception as e:  # noqa: BLE001
                    await outbox.mark_failed(row["id"], str(e))
                    report.failed += 1
                continue

            if existing_hashes.get(pid) == product["content_hash"]:
                await outbox.mark_done(row["id"])
                report.skipped_unchanged += 1
                continue

            needs_embed.append(product)
            needs_embed_outbox_ids.append(row["id"])

        if needs_embed:
            try:
                embedded = await embed_products(needs_embed)
                await store.upsert(embedded)
                for outbox_id in needs_embed_outbox_ids:
                    await outbox.mark_done(outbox_id)
                report.embedded += len(embedded)
            except Exception as e:  # noqa: BLE001
                logger.error("outbox_embed_failed", error=str(e))
                for outbox_id in needs_embed_outbox_ids:
                    await outbox.mark_failed(outbox_id, str(e))
                report.failed += len(needs_embed_outbox_ids)

    logger.info(
        "outbox_drain_complete",
        claimed=report.claimed, embedded=report.embedded,
        skipped_unchanged=report.skipped_unchanged, deleted=report.deleted, failed=report.failed,
    )
    return report
