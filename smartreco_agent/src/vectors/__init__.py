"""Vector store access, reached only through the VectorStore protocol.

No file outside this package references the `vectors` schema directly - see
ARCHITECTURE.md \u00a75.1. `PgVectorStore` is the shipped implementation; swapping in
Qdrant or Pinecone means writing one new class against `VectorStore`.
"""
