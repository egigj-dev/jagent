# Daily outcome tests; temporary audit tables and fake operations isolate source and stage failures from external services.
from contextlib import nullcontext
import os
from pathlib import Path
from unittest.mock import Mock

import pytest

from jagent import health, pipeline, runner
from jagent.db import connect


def source(name, status="ok", fetched=10):
    return {"source": name, "status": status, "fetched": fetched, "new": 0}


@pytest.mark.parametrize("results,expected", [
    ([source("one"), source("two")], "success"),
    ([source("one"), source("timeout", "error", 0)], "degraded"),
    ([source("one"), source("two", "error", 0), source("three", "error", 0)], "degraded"),
    ([source("empty", fetched=0), source("timeout", "error", 0)], "failed"),
    ([source("empty", fetched=0)], "failed"),
    ([], "failed"),
])
def test_collection_coverage_floor(results, expected):
    assert pipeline.collection_outcome(results)["outcome"] == expected


@pytest.mark.parametrize("failures,attempted,expected", [(0, 0, "success"), (1, 10, "degraded"),
                                                         (2, 10, "failed"), (1, 1, "failed")])
def test_processing_retains_existing_failure_tolerance(failures, attempted, expected):
    assert pipeline.processing_outcome(failures, attempted) == expected


@pytest.fixture
def audit_db(monkeypatch):
    if os.environ.get("JAGENT_TEST_POSTGRES") != "1":
        pytest.skip("Set JAGENT_TEST_POSTGRES=1 to use temporary audit tables")
    schema = (Path(__file__).resolve().parents[1] / "schema.sql").read_text()
    with connect() as connection:
        for name in ("source_runs", "pipeline_runs"):
            start = schema.index(f"CREATE TABLE IF NOT EXISTS {name} (")
            connection.execute(schema[start:schema.index(';', start) + 1].replace(
                'CREATE TABLE IF NOT EXISTS', 'CREATE TEMP TABLE'))
        for module in (pipeline, runner, health):
            monkeypatch.setattr(module, "connect", lambda: nullcontext(connection))
        monkeypatch.setattr(pipeline, "duapune_freshness", lambda: "Fresh: test fixture")
        yield connection


@pytest.mark.parametrize("failed_sources,critical_failure,empty,expected", [
    (0, None, False, "success"),
    (1, None, False, "degraded"),
    (3, None, False, "degraded"),
    (0, "matching", False, "failed"),
    (0, "analysis", False, "failed"),
    (1, None, True, "failed"),
])
def test_daily_records_outcome_and_retains_source_errors(audit_db, monkeypatch, failed_sources,
                                                        critical_failure, empty, expected):
    def timeout():
        raise TimeoutError("Source read timed out")

    sources = {"working": lambda: [] if empty else [object()]}
    sources.update({f"broken-{index}": timeout for index in range(failed_sources)})
    monkeypatch.setattr(runner, "SOURCES", sources)
    monkeypatch.setattr(runner, "ats_companies", lambda: [])
    monkeypatch.setattr(runner, "save_postings", lambda connection, postings, seen_at, inserted: len(postings))
    matching = Mock(return_value={"batches_skipped": 0, "batches_attempted": 1})
    analysis = Mock(return_value={"failures": 0, "analyzed": 1})
    diagnostics = Mock(return_value=[])
    if critical_failure:
        (matching if critical_failure == "matching" else analysis).side_effect = RuntimeError("Do not expose secrets")
    monkeypatch.setattr(pipeline, "match", matching)
    monkeypatch.setattr(pipeline, "analyze", analysis)
    monkeypatch.setattr(pipeline, "check_health", diagnostics)

    assert pipeline.daily() == pipeline.EXIT_CODES[expected]
    matching.assert_called_once()
    analysis.assert_called_once()
    diagnostics.assert_called_once()
    row = health.latest_pipeline_run()
    assert row["outcome"] == expected and row["finished_at"] >= row["started_at"]
    assert len(row["stages"]) == 4
    errors = audit_db.execute("SELECT error FROM source_runs WHERE status='error'").fetchall()
    assert errors == [("Source read timed out",)] * failed_sources
    if critical_failure:
        assert "secrets" not in str(row["stages"])
        assert row["stages"][critical_failure]["outcome"] == "failed"
    if expected == "degraded":
        assert any("degraded" in problem for problem in health.operational_problems([], row, "Fresh: test"))


def test_unfinished_run_is_not_reported_as_success(audit_db):
    from datetime import UTC, datetime
    pipeline.start_run(datetime.now(UTC))
    row = health.latest_pipeline_run()
    assert row["outcome"] is None and row["finished_at"] is None
    assert "unfinished" in health.operational_problems([], row, "Fresh: fixture")[0]


def test_systemd_accepts_degraded_exit_without_losing_its_code():
    unit = (Path(__file__).resolve().parents[1] / "deploy/jagent.service").read_text()
    assert "SuccessExitStatus=2" in unit
    assert pipeline.EXIT_CODES == {"success": 0, "degraded": 2, "failed": 1}


def test_duapune_diagnostics_separates_last_success_from_latest_error(audit_db, monkeypatch, tmp_path):
    from datetime import UTC, datetime, timedelta
    import json
    path = tmp_path / 'duapune.json'
    path.write_text(json.dumps({'collected_at': (datetime.now(UTC) - timedelta(hours=37)).isoformat()}))
    monkeypatch.setattr(health.duapune, 'IMPORT_PATH', path)
    audit_db.execute("""
        INSERT INTO source_runs(source,started_at,finished_at,status,fetched,new,error)
        VALUES('duapune',now()-interval '2 hours',now()-interval '1 hour','ok',10,0,NULL),
              ('duapune',now(),now(),'error',0,0,'Import stale')
    """)
    expected = audit_db.execute("SELECT finished_at FROM source_runs WHERE status='ok'").fetchone()[0]
    details = health.duapune_diagnostics()
    assert details['imported_at'] == expected
    assert details['modified_at'].tzinfo == UTC
    assert details['freshness'].startswith('Stale:')
    assert health.latest_source_runs()[0]['status'] == 'error'


def test_health_exception_and_tolerated_processing_failures_are_distinct(audit_db, monkeypatch):
    monkeypatch.setattr(pipeline, 'run', lambda: [source('one')])
    monkeypatch.setattr(pipeline, 'match', lambda: {'batches_skipped': 1, 'batches_attempted': 10})
    monkeypatch.setattr(pipeline, 'analyze', lambda: {'failures': 0, 'analyzed': 0})
    monkeypatch.setattr(pipeline, 'check_health', lambda: [])
    assert pipeline.daily() == 2
    assert health.latest_pipeline_run()['stages']['matching']['outcome'] == 'degraded'
    monkeypatch.setattr(pipeline, 'check_health', Mock(side_effect=RuntimeError('Unavailable')))
    assert pipeline.daily() == 1
    assert health.latest_pipeline_run()['stages']['health']['outcome'] == 'failed'
