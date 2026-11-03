-- Add daily operational history only; existing postings, matches, profiles and reviews remain untouched.
BEGIN;
SET LOCAL lock_timeout = '5s';
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id serial PRIMARY KEY,
    started_at timestamptz NOT NULL,
    finished_at timestamptz,
    outcome text CHECK (outcome IN ('success', 'degraded', 'failed')),
    stages jsonb NOT NULL DEFAULT '{}'
);
COMMIT;
