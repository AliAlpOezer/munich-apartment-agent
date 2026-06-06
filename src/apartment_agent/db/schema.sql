-- Supabase / Postgres schema for the Munich apartment-hunter agent.
-- Apply via the Supabase SQL editor or: psql "$SUPABASE_DB_URL" -f schema.sql

create table if not exists listings (
    id            bigint generated always as identity primary key,
    source        text        not null,              -- e.g. 'wg_gesucht'
    external_id   text        not null,              -- site-native id
    url           text        not null,
    title         text,

    price_warm    numeric,                           -- Warmmiete (EUR/month)
    price_cold    numeric,                           -- Kaltmiete (EUR/month)
    size_sqm      numeric,
    rooms         numeric,
    listing_type  text        not null default 'unknown',  -- wg_room | apartment | unknown

    district      text,
    address       text,
    city          text,

    available_from date,
    available_to   date,
    posted_at      timestamptz,

    fit_score     int,                               -- 0..100, LLM-assigned
    summary       text,                              -- one-line LLM summary
    raw           jsonb       not null default '{}'::jsonb,

    first_seen_at timestamptz not null default now(),
    notified_at   timestamptz,

    unique (source, external_id)
);

-- Fast "what's new / unnotified" lookups
create index if not exists listings_notified_idx   on listings (notified_at);
create index if not exists listings_first_seen_idx  on listings (first_seen_at desc);
create index if not exists listings_fit_idx         on listings (fit_score desc);

-- Per-run metrics (observability / trend history; also feeds the wiki + frontend).
create table if not exists runs (
    id              bigint generated always as identity primary key,
    started_at      timestamptz,
    finished_at     timestamptz,
    duration_ms     numeric,
    scraped         int,
    matched         int,
    new             int,
    notified        int,
    errors          int,
    tokens          jsonb       not null default '{}'::jsonb,   -- {calls,input_tokens,output_tokens}
    node_timings_ms jsonb       not null default '{}'::jsonb,
    error_detail    jsonb       not null default '[]'::jsonb,
    created_at      timestamptz not null default now()
);

create index if not exists runs_created_idx on runs (created_at desc);

-- Human-in-the-loop feedback: which notified message maps to which listing, and the 👍/👎 on it.
create table if not exists notifications (
    message_id    bigint      primary key,        -- Telegram message id
    source        text        not null,
    external_id   text        not null,
    sent_at       timestamptz not null default now()
);

create table if not exists feedback (
    id            bigint generated always as identity primary key,
    source        text        not null,
    external_id   text        not null,
    sentiment     int         not null,           -- +1 like, -1 dislike
    emoji         text,
    update_id     bigint,
    created_at    timestamptz not null default now()
);
create index if not exists feedback_listing_idx on feedback (source, external_id);

-- Tiny key/value store (e.g. the Telegram getUpdates offset).
create table if not exists bot_state (
    key   text primary key,
    value text not null
);
