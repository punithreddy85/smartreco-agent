-- SmartReco: catalog schema
-- Users, products, behavioural events, decayed interest profiles, recommendations,
-- the transactional outbox that drives dual-write sync, the digest queue, and
-- agent_runs (the evidence trail for the trigger policy / efficiency claim).
--
-- Applied in order (also doubles as the Docker `initdb` script). Re-runnable via
-- `create ... if not exists` so it is safe to paste into a fresh Supabase project
-- or mount into a fresh local Postgres container.

create extension if not exists pgcrypto;
create extension if not exists citext;
-- Installed once, into whichever schema is first on search_path (public locally;
-- Supabase's "extensions" schema when enabled from the dashboard - either way it
-- resolves as bare `vector(n)` below because that schema is on search_path).
create extension if not exists vector;

create schema if not exists catalog;

create table if not exists catalog.users (
  id            uuid primary key default gen_random_uuid(),
  email         citext unique not null,
  password_hash text not null,                 -- argon2id
  role          text not null default 'user'
                check (role in ('user','admin')),
  created_at    timestamptz not null default now()
);

create table if not exists catalog.products (
  id           uuid primary key default gen_random_uuid(),
  title        text not null,
  description  text not null,
  category     text not null,
  level        text not null check (level in ('beginner','intermediate','advanced')),
  price_cents  integer not null,
  tags         text[] not null default '{}',
  is_active    boolean not null default true,
  content_hash text not null,                  -- sha256 over embeddable fields
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
create index if not exists products_category_idx on catalog.products (category) where is_active;

create table if not exists catalog.events (
  id          bigserial primary key,
  event_id    uuid unique not null,            -- client-generated; idempotency key
  user_id     uuid not null references catalog.users(id) on delete cascade,
  session_id  uuid not null,
  type        text not null
              check (type in ('page_view','product_view','search',
                              'click','dwell','add_to_cart','dismiss','scroll')),
  product_id  uuid,                            -- nullable; no FK (events outlive products)
  payload     jsonb not null default '{}',
  occurred_at timestamptz not null,            -- client clock
  ingested_at timestamptz not null default now()
);
create index if not exists events_user_time_idx on catalog.events (user_id, occurred_at desc);
create index if not exists events_user_type_time_idx on catalog.events (user_id, type, occurred_at desc);

create table if not exists catalog.user_profiles (
  user_id            uuid primary key references catalog.users(id) on delete cascade,
  weights            jsonb not null default '{}',   -- {category|tag: decayed weight}
  interest_vector    vector(1536),
  gen_vector         vector(1536),                   -- vector at last generation (drift baseline)
  events_since_gen   integer not null default 0,
  last_generated_at  timestamptz,
  profile_hash       text,
  updated_at         timestamptz not null default now()
);

create table if not exists catalog.recommendations (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null references catalog.users(id) on delete cascade,
  narrative      text not null,
  trigger_reason text not null,     -- count | drift | category_shift | scheduled | manual
  profile_hash   text not null,     -- cache key
  model          text not null,
  prompt_version text not null,
  is_current     boolean not null default true,
  created_at     timestamptz not null default now()
);
create unique index if not exists recommendations_current_idx
  on catalog.recommendations (user_id) where is_current;

create table if not exists catalog.recommendation_items (
  rec_id     uuid not null references catalog.recommendations(id) on delete cascade,
  product_id uuid not null,
  rank       smallint not null,
  reason     text not null,
  score      real not null,
  primary key (rec_id, product_id)
);

create table if not exists catalog.vector_outbox (
  id         bigserial primary key,
  product_id uuid not null,
  op         text not null check (op in ('upsert','delete')),
  status     text not null default 'pending'
             check (status in ('pending','done','failed')),
  attempts   smallint not null default 0,
  last_error text,
  created_at timestamptz not null default now()
);
create index if not exists vector_outbox_pending_idx
  on catalog.vector_outbox (status, created_at) where status = 'pending';

create table if not exists catalog.digest_queue (
  user_id     uuid primary key references catalog.users(id) on delete cascade,
  status      text not null default 'pending',
  attempts    smallint not null default 0,
  enqueued_at timestamptz not null default now()
);

create table if not exists catalog.agent_runs (
  id                 bigserial primary key,
  user_id            uuid not null,
  trigger_reason     text not null,
  cache_hit          boolean not null default false,
  refine_loops       smallint not null default 0,
  retrieved_ids      uuid[] not null default '{}',
  node_timings       jsonb not null default '{}',
  model              text,
  prompt_tokens      integer,
  completion_tokens  integer,
  error              text,
  created_at         timestamptz not null default now()
);
create index if not exists agent_runs_created_idx on catalog.agent_runs (created_at desc);
