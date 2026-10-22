-- One row per run; counts are derived from listings, so redelivered messages cannot inflate them.
CREATE TABLE runs (
  id TEXT PRIMARY KEY,
  trigger TEXT NOT NULL CHECK (trigger IN ('cron', 'manual')),
  created_at TEXT NOT NULL,
  criteria TEXT NOT NULL,          -- JSON snapshot of the criteria this run filtered with
  pages_total INTEGER              -- set once by the page-0 handler
);

CREATE TABLE run_pages (
  run_id TEXT NOT NULL REFERENCES runs (id),
  page INTEGER NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('done', 'failed')),
  cards INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  finished_at TEXT NOT NULL,
  PRIMARY KEY (run_id, page)
);

-- The pipeline owns every column except `triage`, which only the dashboard API writes.
CREATE TABLE listings (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL,
  external_id TEXT NOT NULL,
  url TEXT NOT NULL,
  title TEXT,
  listing_type TEXT NOT NULL,
  kind_label TEXT,
  place TEXT,
  street TEXT,
  lat REAL,
  lng REAL,
  price_listed REAL,
  price_warm REAL,
  price_cold REAL,
  size_sqm REAL,
  available_from TEXT,
  available_to TEXT,
  bike_minutes REAL,
  bike_km REAL,
  bike_source TEXT CHECK (bike_source IN ('valhalla', 'estimate')),
  bike_detail TEXT,                -- JSON [{label, minutes, km}] per anchor
  stage TEXT NOT NULL CHECK (stage IN ('pending_detail', 'matched', 'rejected')),
  reasons TEXT NOT NULL DEFAULT '[]',
  detail_status TEXT CHECK (detail_status IN ('ok', 'failed')),
  triage TEXT NOT NULL DEFAULT 'new' CHECK (triage IN ('new', 'seen', 'interested', 'dismissed')),
  first_seen_run TEXT NOT NULL,
  last_seen_run TEXT NOT NULL,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  decided_at TEXT,
  UNIQUE (source, external_id)
);

CREATE INDEX listings_by_stage ON listings (stage, first_seen_at DESC);
CREATE INDEX listings_by_first_run ON listings (first_seen_run);
CREATE INDEX listings_by_last_run ON listings (last_seen_run);
