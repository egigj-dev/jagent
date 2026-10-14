-- Job storage; postings identifies source jobs and source_runs records fetch outcomes.
CREATE EXTENSION IF NOT EXISTS vector;

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
    embedding vector,
    embedding_model text,
    description text,
    first_seen timestamptz DEFAULT now(),
    last_seen timestamptz,
    UNIQUE (source, source_id)
);

ALTER TABLE postings ADD COLUMN IF NOT EXISTS expires_at timestamptz;
ALTER TABLE postings ADD COLUMN IF NOT EXISTS dedupe_key text;
ALTER TABLE postings ADD COLUMN IF NOT EXISTS other_urls text[];
ALTER TABLE postings ADD COLUMN IF NOT EXISTS embedding vector;
ALTER TABLE postings ADD COLUMN IF NOT EXISTS embedding_model text;

CREATE INDEX IF NOT EXISTS postings_dedupe_key_idx ON postings (dedupe_key);

CREATE TABLE IF NOT EXISTS ats_companies (
    platform text,
    slug text,
    added_at timestamptz DEFAULT now(),
    UNIQUE (platform, slug)
);

CREATE TABLE IF NOT EXISTS profile (
    id serial PRIMARY KEY,
    created_at timestamptz DEFAULT now(),
    text text,
    filters jsonb
);

CREATE TABLE IF NOT EXISTS profile_sections (
    id serial PRIMARY KEY,
    profile_id int REFERENCES profile(id),
    name text,
    text text,
    embedding vector,
    embedding_model text
);

CREATE TABLE IF NOT EXISTS matches (
    posting_id int REFERENCES postings(id),
    profile_id int REFERENCES profile(id),
    similarity double precision,
    matched_section text,
    percentile double precision,
    queued bool,
    created_at timestamptz DEFAULT now(),
    UNIQUE (posting_id, profile_id)
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

CREATE TABLE IF NOT EXISTS posting_analysis (
    posting_id int PRIMARY KEY REFERENCES postings(id),
    seniority text,
    required_languages text[],
    employment_types text[],
    salary jsonb,
    evidence jsonb,
    model text,
    analyzed_at timestamptz DEFAULT now()
);

ALTER TABLE matches ADD COLUMN IF NOT EXISTS explanation text;

CREATE TABLE IF NOT EXISTS reviews (
    posting_id int PRIMARY KEY REFERENCES postings(id),
    action text NOT NULL CHECK (action IN ('apply', 'skip', 'later')),
    reason text CHECK (reason IN ('too_senior', 'language', 'location', 'contract', 'salary', 'irrelevant', 'other')),
    note text,
    decided_at timestamptz NOT NULL DEFAULT now(),
    CHECK (action <> 'skip' OR reason IS NOT NULL)
);
