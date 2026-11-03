# Daily outcomes; stages records processing results and pipeline_runs preserves the latest operational verdict.
from datetime import UTC, datetime

from psycopg.types.json import Jsonb

from jagent.analysis import analyze
from jagent.db import connect
from jagent.health import check_health, duapune_freshness
from jagent.matching import match
from jagent.runner import run

EXIT_CODES = {"success": 0, "degraded": 2, "failed": 1}
MAX_FAILURE_RATE = 0.10


def processing_outcome(failures, attempted):
    if not failures:
        return "success"
    if failures == attempted or failures / attempted > MAX_FAILURE_RATE:
        return "failed"
    return "degraded"


def collection_outcome(results):
    usable = sum(result["status"] == "ok" and result["fetched"] > 0 for result in results)
    errors = sum(result["status"] != "ok" for result in results)
    # A completed, nonempty feed is the minimum evidence that this run collected usable data.
    outcome = "failed" if not usable else "degraded" if errors else "success"
    return {"outcome": outcome, "sources": len(results), "usable_sources": usable,
            "failed_sources": errors,
            "message": (f"{usable}/{len(results)} sources returned postings; {errors} failed."
                        + (" No source completed with usable postings." if not usable else ""))}


def overall_outcome(stages):
    outcomes = [stage["outcome"] for stage in stages.values()]
    return "failed" if "failed" in outcomes else "degraded" if "degraded" in outcomes else "success"


def start_run(started_at):
    with connect() as connection:
        return connection.execute(
            "INSERT INTO pipeline_runs (started_at) VALUES (%s) RETURNING id", (started_at,),
        ).fetchone()[0]


def record_progress(run_id, stages, outcome=None):
    with connect() as connection:
        connection.execute(
            "UPDATE pipeline_runs SET stages=%s,outcome=%s,finished_at=%s WHERE id=%s",
            (Jsonb(stages), outcome, datetime.now(UTC) if outcome else None, run_id),
        )


def daily():
    stages = {}
    run_id = start_run(datetime.now(UTC))
    for name, operation in (("collection", run), ("matching", match), ("analysis", analyze),
                            ("health", check_health)):
        print(f"[{datetime.now(UTC):%Y-%m-%dT%H:%M:%SZ}] jagent {name}", flush=True)
        try:
            result = operation()
            if name == "collection":
                for source in result:
                    print(f"{source['source']}: status={source['status']} "
                          f"fetched={source['fetched']} new={source['new']}", flush=True)
                stage = collection_outcome(result)
            elif name in ("matching", "analysis"):
                failed = result["batches_skipped"] if name == "matching" else result["failures"]
                attempted = (result["batches_attempted"] if name == "matching"
                             else result["analyzed"] + failed)
                stage = {"outcome": processing_outcome(failed, attempted),
                         "message": f"{failed}/{attempted} units failed after retries."}
            else:
                freshness = duapune_freshness()
                problems = result + ([] if freshness.startswith("Fresh:") else [f"Duapune import: {freshness}"])
                stage = {"outcome": "degraded" if problems else "success",
                         "message": "; ".join(problems) or "No source health problems."}
        except Exception as error:
            # Provider exceptions may contain secrets; source-specific errors remain in source_runs.
            stage = {"outcome": "failed", "message": f"Stage raised {type(error).__name__}; inspect service logs."}
        stages[name] = stage
        print(f"{name}: {stage['outcome']} — {stage['message']}", flush=True)
        record_progress(run_id, stages)
    outcome = overall_outcome(stages)
    record_progress(run_id, stages, outcome)
    print(f"Pipeline outcome: {outcome}", flush=True)
    return EXIT_CODES[outcome]
