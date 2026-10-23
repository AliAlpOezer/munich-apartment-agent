-- Nearest transit stop by bike (the alternative commute), and the criteria version each decision
-- was made under, so a criteria change re-decides listings that are still online.
ALTER TABLE listings ADD COLUMN stop_label TEXT;
ALTER TABLE listings ADD COLUMN stop_minutes REAL;
ALTER TABLE listings ADD COLUMN stop_km REAL;
ALTER TABLE listings ADD COLUMN criteria_version TEXT;
