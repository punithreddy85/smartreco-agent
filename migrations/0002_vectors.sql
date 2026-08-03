-- SmartReco: vectors schema
--
-- Deliberately isolated from `catalog`: no foreign key to catalog.products, no
-- shared transaction with catalog writes, no cross-schema joins anywhere in the
-- codebase (see ARCHITECTURE.md \u00a75.1). Reached only through the VectorStore
-- protocol in smartreco_agent/src/vectors/.

create schema if not exists vectors;

create table if not exists vectors.product_embeddings (
  product_id   uuid primary key,        -- deliberately NOT a foreign key
  embedding    vector(1536) not null,
  content_hash text not null,
  model        text not null,
  category     text not null,           -- denormalised for metadata pre-filtering
  level        text not null,
  price_cents  integer not null,
  is_active    boolean not null default true,
  updated_at   timestamptz not null default now()
);

create index if not exists product_embeddings_hnsw_idx
  on vectors.product_embeddings
  using hnsw (embedding vector_cosine_ops)
  with (m = 16, ef_construction = 64);

create index if not exists product_embeddings_category_idx
  on vectors.product_embeddings (category) where is_active;
