-- Job storage; postings identifies source jobs and source_runs records fetch outcomes.
CREATE TABLE IF NOT EXISTS postings (
    id serial PRIMARY KEY,
    source text,
    source_id text,
    url text,
    company text,
    title text,
    locations text[],
    remote bool,
    posted_at timestamptz,
    expires_at timestamptz,
    dedupe_key text,
    other_urls text[],
    description text,
    first_seen timestamptz DEFAULT now(),
    last_seen timestamptz,
    UNIQUE (source, source_id)
);

ALTER TABLE postings ADD COLUMN IF NOT EXISTS expires_at timestamptz;
ALTER TABLE postings ADD COLUMN IF NOT EXISTS dedupe_key text;
ALTER TABLE postings ADD COLUMN IF NOT EXISTS other_urls text[];

CREATE TABLE IF NOT EXISTS source_runs (
    id serial PRIMARY KEY,
    source text,
    started_at timestamptz,
    finished_at timestamptz,
    status text CHECK (status IN ('ok', 'error')),
    fetched int,
    new int,
    error text
);
