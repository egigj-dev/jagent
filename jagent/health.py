# Source health checks; latest runs are compared with each source's seven-day median.
from jagent.db import connect


def check_health() -> list[str]:
    with connect() as connection:
        rows = connection.execute(
            """
            WITH latest AS (
                SELECT DISTINCT ON (source) source, status, fetched, error
                FROM source_runs
                ORDER BY source, started_at DESC, id DESC
            ), medians AS (
                SELECT source,
                    percentile_cont(0.5) WITHIN GROUP (ORDER BY fetched) AS median
                FROM source_runs
                WHERE started_at >= now() - interval '7 days'
                  AND started_at <= now()
                GROUP BY source
            )
            SELECT latest.source, status, fetched, error, median
            FROM latest LEFT JOIN medians USING (source)
            ORDER BY latest.source
            """
        ).fetchall()
    problems = []
    for source, status, fetched, error, median in rows:
        reasons = []
        if status == "error":
            reasons.append(f"status=error ({error})" if error else "status=error")
        if fetched == 0:
            reasons.append("fetched=0")
        if median is not None and fetched is not None and fetched < median / 3:
            reasons.append(f"fetched={fetched} below one third of 7-day median={median:g}")
        if reasons:
            problems.append(f"{source}: {'; '.join(reasons)}")
    return problems
