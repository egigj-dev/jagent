# Matching tests; fake embeddings exercise batching, caching and SQL ranking without an embedding API.
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest
import httpx

from jagent import cli, embeddings, matching
from jagent.db import connect


def test_posting_text_strips_html_then_limits_description():
    text = matching.posting_text({
        "title": "Engineer", "company": "Acme", "locations": ["Tirane", "Albania"],
        "description": "<p>" + "x" * 2100 + "</p><p>end</p>",
    })
    assert text == "Engineer\nAcme\nTirane, Albania\n" + "x" * 2000


def test_failed_batch_retries_once_and_continues():
    connection = MagicMock()
    embed = Mock(side_effect=[RuntimeError("secret"), RuntimeError("secret"), ([[1, 0]], 5)])
    rows = [(id, "text") for id in range(101)]
    assert matching.embed_batches(connection, "postings", rows, "fake", embed) == (1, 5, 100)
    assert [len(call.args[0]) for call in embed.call_args_list] == [100, 100, 1]
    assert connection.cursor.return_value.__enter__.return_value.executemany.call_count == 1


def test_transient_failure_is_retried_and_tokens_are_reported():
    embed = Mock(side_effect=[RuntimeError("temporary"), ([[1, 0], [0, 1]], 12)])
    assert matching.embed_batches(MagicMock(), "profile_sections", [(1, "a"), (2, "b")], "fake", embed) == (2, 12, 0)
    assert embed.call_count == 2


def test_rate_limited_batch_waits_then_retries_once(monkeypatch):
    response = httpx.Response(429, headers={"retry-after": "2"},
                             request=httpx.Request("POST", "https://example.invalid/v1/embeddings"))
    error = httpx.HTTPStatusError("hidden body", request=response.request, response=response)
    embed = Mock(side_effect=[error, ([[1, 0]], 3)])
    sleep = Mock()
    monkeypatch.setattr(matching.time, "sleep", sleep)
    assert matching.embed_batches(MagicMock(), "postings", [(1, "a")], "fake", embed) == (1, 3, 0)
    sleep.assert_called_once_with(2)
    assert embed.call_count == 2


def test_provider_uses_only_configured_embeddings_endpoint(monkeypatch):
    settings = {"EMBEDDINGS_BASE_URL": "https://example.invalid/v1",
                "EMBEDDINGS_API_KEY": "fake-key", "EMBEDDINGS_MODEL": "fake-model"}
    response = Mock()
    response.json.return_value = {"data": [
        {"index": 1, "embedding": [0, 1]}, {"index": 0, "embedding": [1, 0]},
    ], "usage": {"total_tokens": 11}}
    post = Mock(return_value=response)
    monkeypatch.setattr(embeddings.httpx, "post", post)
    assert embeddings.embed(["a", "b"], settings) == ([[1, 0], [0, 1]], 11)
    assert post.call_args.args == ("https://example.invalid/v1/embeddings",)
    assert post.call_args.kwargs["json"] == {"model": "fake-model", "input": ["a", "b"]}
    assert post.call_args.kwargs["follow_redirects"] is False


def test_no_credentials_printed_on_failed_batch(capsys):
    fake = Mock(side_effect=ValueError("fake-api-key must never be printed"))
    assert matching.embed_batches(Mock(), "postings", [(1, "text")], "fake", fake) == (0, 0, 1)
    assert "fake-api-key" not in capsys.readouterr().out


@pytest.fixture
def ranking_db(monkeypatch):
    if os.environ.get("JAGENT_TEST_POSTGRES") != "1":
        pytest.skip("Set JAGENT_TEST_POSTGRES=1 to test ranking in isolated temporary tables")
    connection = connect()
    connection.execute("""
        CREATE TEMP TABLE profile (id int, text text, filters jsonb);
        CREATE TEMP TABLE profile_sections
          (id int, profile_id int, name text, text text, embedding vector, embedding_model text);
        CREATE TEMP TABLE postings (
          id int, title text, company text, locations text[], remote bool, description text,
          expires_at timestamptz, posted_at timestamptz, first_seen timestamptz,
          embedding vector, embedding_model text, dedupe_key text);
        CREATE TEMP TABLE matches (
          posting_id int, profile_id int, similarity double precision, matched_section text,
          percentile double precision, queued bool, created_at timestamptz DEFAULT now(),
          UNIQUE(posting_id, profile_id));
        INSERT INTO profile VALUES (1, 'Sample profile',
          '{"countries":["albania"],"remote_regions":["europe"],"remote_excluded":[],"exclude_title_keywords":[]}');
        INSERT INTO profile_sections (id, profile_id, name, text)
          VALUES (1,1,'Engineering','Python'), (2,1,'Security','Detection');
    """)
    now = datetime.now(UTC)
    for id, title, locations, date in [
        (1, "Engineer", ["Albania"], now),
        (2, "Developer", ["Albania"], now),
        (3, "Other", ["Albania"], now),
        (4, "Excluded", ["Japan"], now),
        (5, "Expired", ["Albania"], now - timedelta(days=31)),
    ]:
        connection.execute(
            "INSERT INTO postings (id,title,company,locations,remote,description,first_seen) "
            "VALUES (%s,%s,'Acme',%s,false,'description',%s)", (id, title, locations, date),
        )
    connection.commit()
    monkeypatch.setattr(matching, "connect", lambda: nullcontext(connection))
    yield connection
    connection.close()


def fake_embed(texts):
    vectors = {"Engineering": [1, 0], "Security": [0, 1],
               "Engineer": [1, 0], "Developer": [0.8, 0.6], "Other": [-1, 0]}
    return [vectors[text.splitlines()[0]] for text in texts], len(texts) * 3


def test_real_sql_ranking_and_model_cache(ranking_db, capsys):
    settings = {"EMBEDDINGS_MODEL": "fake-v1"}
    result = matching.match(fake_embed, settings)
    assert result == {"sections_embedded": 2, "postings_embedded": 3, "scored": 3,
                      "queued": 1, "tokens": 15, "skipped": 0,
                      "batches_attempted": 2, "batches_skipped": 0}
    rows = ranking_db.execute(
        "SELECT posting_id,similarity,matched_section,percentile,queued FROM matches ORDER BY posting_id"
    ).fetchall()
    assert rows[0] == (1, 1.0, "Engineering", 100.0, True)
    assert rows[1][1] == pytest.approx(0.8)
    assert rows[1][2:] == ("Engineering", 50.0, False)
    assert rows[2] == (3, 0.0, "Security", 0.0, False)
    assert "Engineering: 1" in capsys.readouterr().out
    cached = matching.match(Mock(side_effect=AssertionError("Cached rows must not re-embed")), settings)
    assert cached["postings_embedded"] == cached["sections_embedded"] == cached["tokens"] == 0
    assert cached["batches_attempted"] == cached["batches_skipped"] == 0
    changed = matching.match(fake_embed, {"EMBEDDINGS_MODEL": "fake-v2"})
    assert changed["sections_embedded"] == 2 and changed["postings_embedded"] == 3
    assert ranking_db.execute("SELECT count(*) FROM matches").fetchone()[0] == 3


def test_failed_posting_batch_is_picked_up_next_run(ranking_db):
    fake = Mock(side_effect=[([[1, 0], [0, 1]], 6), RuntimeError("fail"), RuntimeError("fail")])
    settings = {"EMBEDDINGS_MODEL": "fake"}
    first = matching.match(fake, settings)
    assert first["skipped"] == 3 and first["scored"] == 0
    assert first["batches_attempted"] == 2 and first["batches_skipped"] == 1
    second = matching.match(fake_embed, settings)
    assert second["sections_embedded"] == 0 and second["postings_embedded"] == 3
    assert second["scored"] == 3


def test_match_cli(monkeypatch):
    run_match = Mock(return_value={"batches_skipped": 0, "batches_attempted": 0})
    monkeypatch.setattr(cli, "match", run_match)
    monkeypatch.setattr("sys.argv", ["jagent", "match"])
    assert cli.main() == 0
    run_match.assert_called_once_with()


@pytest.mark.parametrize("attempted,skipped,exit_code", [
    (83, 1, 0), (10, 2, 1), (3, 3, 1), (10, 1, 0), (100, 11, 1),
    (0, 0, 0), (83, 0, 0),
])
def test_match_cli_failure_rate(monkeypatch, capsys, attempted, skipped, exit_code):
    monkeypatch.setattr(cli, "match", lambda: {
        "batches_skipped": skipped, "batches_attempted": attempted,
    })
    monkeypatch.setattr("sys.argv", ["jagent", "match"])
    assert cli.main() == exit_code
    assert capsys.readouterr().out == (f"warning: {skipped} retried next run\n" if skipped else "")


def test_queue_thresholds_require_both_percentile_and_similarity(ranking_db):
    assert matching.QUEUE_MIN_PERCENTILE == 97
    assert matching.QUEUE_MIN_SIMILARITY == 0.55
    ranking_db.execute("UPDATE profile_sections SET embedding='[1,0]', embedding_model='fake' WHERE id=1")
    ranking_db.execute("UPDATE postings SET embedding='[0,1]',embedding_model='fake'")
    # The strongest score has percentile 100 but similarity .5, so must not queue.
    ranking_db.execute("UPDATE postings SET embedding='[0.5,0.8660254]' WHERE id=1")
    assert matching.score_postings(ranking_db, [1,2,3], 1, "fake", datetime.now(UTC)) == (3,0)
    # A strong score can still miss the percentile threshold; only the highest queues.
    ranking_db.execute("UPDATE postings SET embedding='[1,0]' WHERE id=1")
    ranking_db.execute("UPDATE postings SET embedding='[0.8,0.6]' WHERE id=2")
    assert matching.score_postings(ranking_db, [1,2,3], 1, "fake", datetime.now(UTC)) == (3,1)
    assert ranking_db.execute("SELECT queued FROM matches WHERE posting_id=2").fetchone() == (False,)


def test_dedupe_index_is_non_unique_and_idempotent(ranking_db):
    schema = (Path(__file__).resolve().parent.parent / "schema.sql").read_text()
    statement = next(line for line in schema.splitlines() if line.startswith("CREATE INDEX IF NOT EXISTS postings_dedupe_key_idx"))
    ranking_db.execute(statement)
    ranking_db.execute(statement)
    assert ranking_db.execute(
        "SELECT i.indisunique, pg_get_indexdef(i.indexrelid, 1, true) "
        "FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid "
        "WHERE i.indrelid='pg_temp.postings'::regclass AND c.relname='postings_dedupe_key_idx'"
    ).fetchone() == (False, "dedupe_key")


@pytest.mark.parametrize("failed_table", ["profile_sections", "postings"])
def test_match_counts_partial_failed_batches(ranking_db, monkeypatch, failed_table):
    # A failed single-row tail is one of two posting batches, not one of 101 requests.
    ranking_db.execute("DELETE FROM postings")
    ranking_db.execute("""
        INSERT INTO postings (id,title,company,locations,remote,description,first_seen)
        SELECT id,'Engineer','Acme','{Albania}',false,'description',now()
        FROM generate_series(1,101) AS id
    """)
    calls = 0

    def embed(texts):
        nonlocal calls
        calls += 1
        if failed_table == "profile_sections" and texts[0].startswith("Engineering"):
            raise RuntimeError("Unavailable")
        if failed_table == "postings" and len(texts) == 1:
            raise RuntimeError("Unavailable")
        return [[1, 0] for _ in texts], 0

    result = matching.match(embed, {"EMBEDDINGS_MODEL": "fake"})
    assert calls == 4  # Three batches, with one retried request.
    assert result["batches_attempted"] == 3
    assert result["batches_skipped"] == 1
    assert result["skipped"] == (2 if failed_table == "profile_sections" else 1)
