-- Frozen sampling; as_of and profile_id bind the window, six near rows precede fourteen percentile targets.
WITH recent AS (
    SELECT p.id, p.source, p.source_id, p.title, p.company, p.description,
           p.locations, p.url, m.similarity, m.percentile, m.queued,
           coalesce(p.posted_at, p.first_seen) AS posting_date
    FROM postings p JOIN matches m ON m.posting_id = p.id
    WHERE m.profile_id = %(profile_id)s
      AND coalesce(p.posted_at, p.first_seen)
          BETWEEN %(as_of)s::timestamptz - interval '30 days' AND %(as_of)s::timestamptz
      AND p.description IS NOT NULL
      AND length(p.company) >= 4
      AND lower(p.company) NOT IN (
          'docker', 'oracle', 'google', 'microsoft', 'meta', 'code', 'provide',
          'applied', 'fluent', 'most', 'openai', 'cloudera', 'genesys', 'mistral.ai',
          'snowflake', 'databricks', 'salesforce', 'servicenow', 'laravel', 'livewire'
      )
), near AS (
    SELECT * FROM recent
    WHERE similarity >= %(min_similarity)s
    ORDER BY abs(percentile - %(min_percentile)s), id
    LIMIT 6
), spread AS (
    SELECT picked.*
    FROM generate_series(0, 13) AS target(n)
    CROSS JOIN LATERAL (
        SELECT recent.* FROM recent
        WHERE id NOT IN (SELECT id FROM near)
        ORDER BY abs(percentile - target.n * 100.0 / 13), id
        LIMIT 1
    ) picked
)
SELECT *, 'near_cutoff' AS selection FROM near
UNION ALL
SELECT *, 'spread' AS selection FROM spread
ORDER BY similarity, id;
