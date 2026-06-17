create extension if not exists vector with schema extensions;

create table if not exists documents (
  id uuid primary key,
  filename text not null,
  sha256 text not null unique,
  status text not null default 'uploaded',
  source_uri text,
  year integer,
  page_count integer default 0,
  draft jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists pages (
  id bigint primary key generated always as identity,
  document_id uuid not null references documents(id) on delete cascade,
  page_number integer not null,
  route text not null,
  quality_score numeric,
  ocr_confidence numeric,
  text_content text,
  image_uri text,
  warnings jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  unique(document_id, page_number)
);

create table if not exists extraction_runs (
  id uuid primary key,
  document_id uuid not null references documents(id) on delete cascade,
  status text not null,
  model text,
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  error text,
  metrics jsonb not null default '{}'::jsonb
);

create table if not exists extracted_fields (
  id bigint primary key generated always as identity,
  document_id uuid not null references documents(id) on delete cascade,
  label text not null,
  value_raw text,
  value_normalized text,
  value_type text,
  section text,
  page integer,
  confidence numeric,
  bbox jsonb,
  evidence text,
  source text,
  reviewer_state text not null default 'approved',
  created_at timestamptz not null default now()
);

create table if not exists extracted_tables (
  id bigint primary key generated always as identity,
  document_id uuid not null references documents(id) on delete cascade,
  title text,
  page integer,
  rows jsonb not null default '[]'::jsonb,
  confidence numeric,
  source text,
  created_at timestamptz not null default now()
);

create table if not exists document_chunks (
  id uuid primary key,
  document_id uuid not null references documents(id) on delete cascade,
  chunk_index integer not null,
  content text not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique(document_id, chunk_index)
);

create table if not exists document_embeddings (
  chunk_id uuid primary key references document_chunks(id) on delete cascade,
  document_id uuid not null references documents(id) on delete cascade,
  embedding extensions.vector(1536),
  model text not null,
  created_at timestamptz not null default now()
);

create index if not exists extracted_fields_document_id_idx on extracted_fields(document_id);
create index if not exists extracted_fields_label_idx on extracted_fields(label);
create index if not exists document_chunks_document_id_idx on document_chunks(document_id);
create index if not exists document_embeddings_vector_idx
  on document_embeddings using hnsw (embedding extensions.vector_cosine_ops);

create or replace function match_document_chunks(
  query_embedding extensions.vector(1536),
  match_count integer default 10
)
returns table (
  document_id uuid,
  chunk_id uuid,
  content text,
  metadata jsonb,
  similarity double precision
)
language sql stable
as $$
  select
    dc.document_id,
    dc.id as chunk_id,
    dc.content,
    dc.metadata,
    1 - (de.embedding <=> query_embedding) as similarity
  from document_embeddings de
  join document_chunks dc on dc.id = de.chunk_id
  where de.embedding is not null
  order by de.embedding <=> query_embedding
  limit match_count;
$$;
