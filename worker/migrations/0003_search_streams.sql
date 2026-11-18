-- Search streams: a run walks one result list per source category. A page row is claimed
-- ('queued') in the step that enqueues its job, so a page linked from several pages is fetched
-- once, and a run is complete when no page is queued. This replaces runs.pages_total.
CREATE TABLE run_pages_v3 (
  run_id TEXT NOT NULL REFERENCES runs (id),
  stream TEXT NOT NULL,
  page INTEGER NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('queued', 'done', 'failed')),
  cards INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  queued_at TEXT,
  finished_at TEXT,
  PRIMARY KEY (run_id, stream, page)
);

INSERT INTO run_pages_v3 (run_id, stream, page, status, cards, error, finished_at)
  SELECT run_id, 'wg_gesucht', page, status, cards, error, finished_at FROM run_pages;

DROP TABLE run_pages;
ALTER TABLE run_pages_v3 RENAME TO run_pages;
ALTER TABLE runs DROP COLUMN pages_total;

-- Flat swap (Tausch): the title says so, or the detail page's Tauschangebot attribute does.
ALTER TABLE listings ADD COLUMN swap INTEGER NOT NULL DEFAULT 0 CHECK (swap IN (0, 1));
