-- SmartReco: richer product detail content (BUGFIX.md P2.4)
--
-- Adds "what you'll learn" outcomes plus duration/module count so the
-- product detail page has real content instead of ~65% empty space. These
-- are also folded into `content_hash` / the embedded text, so they improve
-- retrieval quality too, not just the page layout.
--
-- Re-runnable via `add column if not exists`, consistent with 0001/0002.

alter table catalog.products
  add column if not exists learning_outcomes text[] not null default '{}',
  add column if not exists duration_minutes integer,
  add column if not exists module_count integer;
