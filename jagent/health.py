# Source health checks; full feeds use yield rules, incremental feeds use errors, non-ATS runs must be fresh.
from datetime import UTC, datetime
import json

from psycopg.rows import dict_row

from jagent.db import connect
from jagent.sources import duapune

WARNING_ONLY_SOURCES = frozenset({"duapune"})


def check_health() -> list[str]:
    with connect() as connection:
        rows = connection.execute(
            """
            WITH latest AS (
                SELECT DISTINCT ON (source) source, status, fetched, error, started_at
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
            SELECT latest.source, status, fetched, error, median,
                   started_at < now() - interval '36 hours' AS stale
            FROM latest LEFT JOIN medians USING (source)
            ORDER BY latest.source
            """
        ).fetchall()
    problems = []
    ats_errors = []
    ats_total = 0
    for source, status, fetched, error, median, stale in rows:
        if source.startswith("ats:"):
            ats_total += 1
            if status == "error":
                platform, slug = source.split(":", 2)[1:]
                ats_errors.append(f"{platform}/{slug}")
                continue
            continue
        reasons = []
        if status == "error":
            reasons.append(f"status=error ({error})" if error else "status=error")
        if stale:
            reasons.append("stale (latest run older than 36 hours)")
        if source not in ("himalayas", "djinni") and fetched == 0:
            reasons.append("fetched=0")
        if source not in ("himalayas", "djinni") and median is not None and fetched is not None and fetched < median / 3:
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


def latest_source_runs():
    with connect() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            return cursor.execute("""
                SELECT DISTINCT ON (source)
                    source, status, finished_at, fetched, error
                FROM source_runs
                ORDER BY source, started_at DESC, id DESC
            """).fetchall()


def duapune_freshness(now=None):
    now = now or datetime.now(UTC)
    try:
        data = json.loads(duapune.IMPORT_PATH.read_text())
        collected_at = duapune.collected_time(data, now)
    except FileNotFoundError:
        return "Missing"
    except OSError:
        return "Unreadable import file"
    except (ValueError, KeyError, TypeError):
        return "Invalid import timestamp or JSON"
    collected_at = collected_at.astimezone(UTC)
    status = "Stale" if now - collected_at > duapune.MAX_IMPORT_AGE else "Fresh"
    return f"{status}: collected at {collected_at:%Y-%m-%d %H:%M:%S} UTC"


def latest_pipeline_run():
    with connect() as connection:
        # Older deployments remain readable before the new, additive table is initialized.
        if connection.execute("SELECT to_regclass('pipeline_runs')").fetchone()[0] is None:
            return None
        with connection.cursor(row_factory=dict_row) as cursor:
            return cursor.execute(
                "SELECT started_at,finished_at,outcome,stages FROM pipeline_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()


def operational_problems(source_problems, pipeline_run, freshness):
    problems = list(source_problems)
    if pipeline_run and pipeline_run["outcome"] != "success":
        outcome = pipeline_run["outcome"] or "unfinished (running or interrupted)"
        problems.append(f"Latest daily pipeline: {outcome}; see Source health for stage details.")
    if not freshness.startswith("Fresh:"):
        problems.append(f"Duapune import: {freshness}")
    return problems


def duapune_diagnostics():
    try:
        modified_at = datetime.fromtimestamp(duapune.IMPORT_PATH.stat().st_mtime, UTC)
    except OSError:
        modified_at = None
    with connect() as connection:
        if connection.execute("SELECT to_regclass('source_runs')").fetchone()[0] is None:
            imported_at = None
        else:
            imported_at = connection.execute(
                "SELECT max(finished_at) FROM source_runs WHERE source='duapune' AND status='ok'"
            ).fetchone()[0]
    return {"freshness": duapune_freshness(), "modified_at": modified_at,
            "imported_at": imported_at}
