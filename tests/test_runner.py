# Runner isolation test; recorded holds audit rows from failed and successful sources.
from contextlib import nullcontext
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from jagent import runner
from jagent.models import Posting


def test_failing_source_does_not_stop_others(monkeypatch):
    recorded = []

    def fail():
        raise RuntimeError("Source unavailable")

    monkeypatch.setattr(runner, "SOURCES", {"broken": fail, "working": lambda: []})
    monkeypatch.setattr(runner, "connect", lambda: nullcontext(None))
    monkeypatch.setattr(runner, "record_run", lambda connection, result:
                        recorded.append(result.copy()))
    results = runner.run()
    assert [result["status"] for result in results] == ["error", "ok"]
    assert recorded == results
    assert recorded[0]["error"] == "Source unavailable"
    assert recorded[0]["new"] == 0
    assert recorded[1]["error"] is None


@pytest.mark.parametrize("sources", [("one", "one"), ("one", "two")])
def test_duplicate_jobs_save_as_one_row(sources):
    rows = []

    def execute(query, params=None):
        result = Mock()
        if "WHERE dedupe_key = %s" in query:
            row = next((row for row in rows if row["dedupe_key"] == params[0]), None)
            result.fetchone.return_value = (
                row["id"], row["url"], row["other_urls"], row["locations"]
            ) if row else None
        elif "INSERT INTO postings" in query:
            rows.append({**params, "id": len(rows) + 1})
            result.fetchone.return_value = (rows[-1]["id"],)
        elif "SET other_urls" in query:
            row = next(row for row in rows if row["id"] == params["id"])
            row.update(other_urls=params["other_urls"], locations=params["locations"])
        else:
            raise AssertionError(query)
        return result

    connection = Mock()
    connection.execute.side_effect = execute
    postings = [
        Posting(
            source=sources[0], source_id="first", url="https://one.example/job",
            company="Example, Inc.", title="Senior  Engineer", locations=["Berlin"],
        ),
        Posting(
            source=sources[1], source_id="second", url="https://two.example/job",
            company="example inc", title="Senior Engineer!", locations=["Remote"],
        ),
    ]
    assert runner.save_postings(
        connection, postings, datetime(2026, 10, 5, tzinfo=UTC)
    ) == 1
    assert len(rows) == 1
    assert rows[0]["other_urls"] == ["https://two.example/job"]
    assert rows[0]["locations"] == ["Berlin", "Remote"]
