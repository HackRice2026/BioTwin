-- Precomputed narration grounding: short natural-language facts distilled from the
-- locked MATLAB model-comparison results (matlab/results/BASELINES.md), each embedded
-- so narration/insights.py can retrieve the one relevant fact by similarity instead of
-- the coach having no way to ground a forecast-accuracy question at all. Populated by
-- `uv run python -m scripts.generate_insights`, never written from a live request.
--
-- The embedding is a plain JSON float array rather than a native pgvector column: this
-- corpus is a handful of rows, an ANN index buys nothing at that size, and a JSON column
-- keeps this table on the same SQLAlchemy Core schema as the SQLite dev database (see
-- core/store.py) instead of a second, Postgres-only code path.
create table if not exists public.analysis_insights (
    topic text primary key,
    content text not null,
    source_numbers jsonb not null,
    embedding jsonb not null
);

-- Defense in depth: BioTwin's FastAPI server is the only supported data API.
alter table public.analysis_insights enable row level security;
revoke all on table public.analysis_insights from anon, authenticated;
