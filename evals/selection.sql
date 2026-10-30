-- Frozen queued sampling; as_of and profile_id bind the window, rank targets spread seven borderline and thirteen upper rows.
WITH recent AS (
    SELECT p.id, p.source, p.source_id, p.title, p.company, p.description,
           p.locations, p.url, m.similarity, m.percentile, m.queued,
           coalesce(p.posted_at, p.first_seen) AS posting_date
    FROM postings p JOIN matches m ON m.posting_id = p.id
    WHERE m.profile_id = %(profile_id)s
      AND m.queued
      AND m.percentile >= %(min_percentile)s
      AND m.similarity >= %(min_similarity)s
      AND coalesce(p.posted_at, p.first_seen)
          BETWEEN %(as_of)s::timestamptz - interval '30 days' AND %(as_of)s::timestamptz
      AND p.description IS NOT NULL
      AND length(p.company) >= 4
      AND lower(p.company) NOT IN (
          'docker', 'oracle', 'google', 'microsoft', 'meta', 'code', 'provide',
          'applied', 'fluent', 'most', 'openai', 'cloudera', 'genesys', 'mistral.ai',
          'snowflake', 'databricks', 'salesforce', 'servicenow', 'laravel', 'livewire'
      )
), bands AS (
    SELECT *, CASE WHEN percentile < 98 THEN 'borderline' ELSE 'upper' END AS selection,
           CASE WHEN percentile < 98 THEN 7 ELSE 13 END AS sample_size
    FROM recent
), ranked AS (
    SELECT *, row_number() OVER (PARTITION BY selection ORDER BY percentile, id) AS sample_rank,
           count(*) OVER (PARTITION BY selection) AS sample_count
    FROM bands
)
SELECT id, source, source_id, title, company, description, locations, url,
       similarity, percentile, queued, posting_date, selection
FROM ranked
WHERE sample_rank IN (
    SELECT 1 + round(n * (sample_count - 1)::numeric / (sample_size - 1))
    FROM generate_series(0, sample_size - 1) AS target(n)
)
ORDER BY percentile, id;
