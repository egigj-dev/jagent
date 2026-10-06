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
    ats_errors = []
    ats_total = 0
    for source, status, fetched, error, median in rows:
        if source.startswith("ats:"):
            ats_total += 1
            if status == "error":
                platform, slug = source.split(":", 2)[1:]
                ats_errors.append(f"{platform}/{slug}")
                continue
            if median is not None and fetched is not None and fetched < median / 3:
                problems.append(
                    f"{source}: fetched={fetched} below one third of 7-day median={median:g}"
                )
            continue
        reasons = []
        if status == "error":
            reasons.append(f"status=error ({error})" if error else "status=error")
        if fetched == 0:
            reasons.append("fetched=0")
        if median is not None and fetched is not None and fetched < median / 3:
            reasons.append(f"fetched={fetched} below one third of 7-day median={median:g}")
        if reasons:
            problems.append(f"{source}: {'; '.join(reasons)}")
    if ats_errors:
        listed = ", ".join(ats_errors[:5])
        suffix = "" if len(ats_errors) <= 5 else ", ..."
        problems.append(
            f"ats: {len(ats_errors)} of {ats_total} boards failed ({listed}{suffix})"
        )
    return problems
