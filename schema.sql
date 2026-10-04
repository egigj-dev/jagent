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
    description text,
    first_seen timestamptz DEFAULT now(),
    last_seen timestamptz,
    UNIQUE (source, source_id)
);

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
