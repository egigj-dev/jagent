# Runner isolation test; recorded holds audit rows from failed and successful sources.
from contextlib import nullcontext
from datetime import UTC, datetime
import os
from pathlib import Path
from unittest.mock import Mock

import pytest

from jagent import runner
from jagent.models import Posting
from jagent.db import connect


def test_failing_source_does_not_stop_others(monkeypatch):
    recorded = []

    def fail():
        raise RuntimeError("Source unavailable")

    monkeypatch.setattr(runner, "SOURCES", {"broken": fail, "working": lambda: []})
    monkeypatch.setattr(runner, "connect", lambda: nullcontext(None))
    monkeypatch.setattr(runner, "ats_companies", lambda: [])
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
            row.update(other_urls=params["other_urls"], locations=params["locations"],
                       remote=params["remote"])
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
            remote=True,
        ),
    ]
    assert runner.save_postings(
        connection, postings, datetime(2026, 10, 5, tzinfo=UTC)
    ) == 1
    assert len(rows) == 1
    assert rows[0]["other_urls"] == ["https://two.example/job"]
    assert rows[0]["locations"] == ["Berlin", "Remote"]
    assert rows[0]["remote"] is True


@pytest.mark.parametrize("existing_remote", [None, False, True])
def test_duplicate_with_null_remote_in_postgres(existing_remote):
    if os.environ.get("JAGENT_TEST_POSTGRES") != "1":
        pytest.skip("Set JAGENT_TEST_POSTGRES=1 to test persistence in a temporary table")
    with connect() as connection:
        connection.execute("""
            CREATE TEMP TABLE postings (
                id serial PRIMARY KEY, source text, source_id text, url text,
                company text, title text, locations text[], remote bool,
                posted_at timestamptz, expires_at timestamptz, dedupe_key text,
                other_urls text[], description text, first_seen timestamptz,
                last_seen timestamptz, UNIQUE(source, source_id)
            )
        """)
        first = Posting(
            source="hn_hiring", source_id="49922593",
            company="Shepherd (Series B)", title="ONSITE",
            url="https://news.ycombinator.com/item?id=49922593",
            locations=["London"], remote=existing_remote,
        )
        duplicate = first.model_copy(update={
            "source_id": "duplicate", "url": "https://example.com/job",
            "locations": ["Berlin"], "remote": None,
        })
        first_seen = datetime(2026, 10, 11, tzinfo=UTC)
        last_seen = datetime(2026, 10, 12, tzinfo=UTC)
        assert runner.save_postings(connection, [first], first_seen) == 1
        assert runner.save_postings(connection, [duplicate], last_seen) == 0
        assert connection.execute(
            "SELECT remote, other_urls, locations, first_seen, last_seen FROM postings"
        ).fetchall() == [(
            existing_remote, [duplicate.url], ["London", "Berlin"],
            first_seen, last_seen,
        )]


def test_source_failure_preserves_successful_postings(monkeypatch):
    if os.environ.get("JAGENT_TEST_POSTGRES") != "1":
        pytest.skip("Set JAGENT_TEST_POSTGRES=1 to test source isolation in temporary tables")
    with connect() as connection:
        schema = (Path(__file__).resolve().parent.parent / "schema.sql").read_text()
        for name in ("postings", "source_runs", "ats_companies"):
            start = schema.index(f"CREATE TABLE IF NOT EXISTS {name} (")
            statement = schema[start:schema.index(";", start) + 1]
            connection.execute(statement.replace("CREATE TABLE IF NOT EXISTS", "CREATE TEMP TABLE"))
        monkeypatch.setattr(runner, "connect", lambda: nullcontext(connection))

        def fail():
            raise RuntimeError("Source unavailable")

        posting = Posting(source="working", source_id="1", title="Engineer",
                          company="Example", url="https://example.com/job")
        monkeypatch.setattr(runner, "SOURCES", {
            "broken": fail, "working": lambda: [posting],
        })
        results = runner.run()
        assert [result["status"] for result in results] == ["error", "ok"]
        assert connection.execute("SELECT source, source_id, title FROM postings").fetchall() == [
            ("working", "1", "Engineer"),
        ]
        assert connection.execute(
            "SELECT source, status, fetched, new, error FROM source_runs ORDER BY id"
        ).fetchall() == [
            ("broken", "error", 0, 0, "Source unavailable"),
            ("working", "ok", 1, 1, None),
        ]
        assert all(result["finished_at"] >= result["started_at"] for result in results)
