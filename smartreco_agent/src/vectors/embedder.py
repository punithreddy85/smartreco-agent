"""Turns catalog products into embeddings via Mesh, ready for the vector store.

Batches aggressively: one Mesh call per outbox chunk (up to 50 products), not
one per product (Appendix D.4).
"""

from __future__ import annotations

from typing import Sequence

from smartreco_agent.src.db.hashing import content_hash, embeddable_text
from smartreco_agent.src.mesh.client import embed
from smartreco_agent.src.settings import settings
from smartreco_agent.src.vectors.protocol import EmbeddedProduct


async def embed_products(products: Sequence[dict]) -> list[EmbeddedProduct]:
    """`products` are `catalog.products` rows (dicts). Returns one EmbeddedProduct
    per input row, in the same order."""
    if not products:
        return []

    texts = [
        embeddable_text(
            title=p["title"], description=p["description"],
            category=p["category"], level=p["level"], tags=p["tags"],
        )
        for p in products
    ]
    vectors = await embed(texts, input_type="document")

    return [
        EmbeddedProduct(
            product_id=str(p["id"]),
            embedding=vector,
            content_hash=content_hash(
                title=p["title"], description=p["description"],
                category=p["category"], level=p["level"], tags=p["tags"],
            ),
            model=settings.MESH_EMBED_MODEL,
            category=p["category"],
            level=p["level"],
            price_cents=p["price_cents"],
            is_active=p["is_active"],
        )
        for p, vector in zip(products, vectors)
    ]
