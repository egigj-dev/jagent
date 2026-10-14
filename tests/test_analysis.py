# Analysis tests; fake chat responses exercise validation and isolated Postgres tables verify caching.
from contextlib import nullcontext
import json
import os
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from jagent import analysis, cli
from jagent.db import connect


def facts(**changes):
    return {"seniority": "mid", "required_languages": ["English"],
            "employment_types": ["full_time"],
            "salary": {"min": 100, "max": 200, "currency": "EUR", "period": "year"},
            "evidence": {"seniority": "mid", "required_languages": "English",
                         "employment_types": "full time", "salary": "100-200 EUR/year"},
            "explanation": "Python matches the section. Cloud experience is missing.", **changes}


@pytest.mark.parametrize("changes", [
    {"seniority": "director"}, {"employment_types": ["permanent"]},
    {"required_languages": "English"}, {"salary": {"min": "lots"}},
    {"evidence": {}}, {"explanation": ""}, {"unexpected": True},
])
def test_invalid_facts(changes):
    with pytest.raises(ValidationError):
        analysis.Analysis.model_validate_json(json.dumps(facts(**changes)))


def test_unstated_facts_and_no_required_languages():
    for languages in ([], None):
        result = analysis.Analysis.model_validate_json(json.dumps(facts(
            seniority="unknown", required_languages=languages,
            employment_types=None, salary=None, evidence={"salary": None},
        )))
        assert result.required_languages == languages


def test_chat_endpoint_and_content_only(monkeypatch):
    settings = {"LLM_BASE_URL": "https://example.invalid/v1",
                "LLM_API_KEY": "fake-key", "LLM_MODEL": "fake"}
    response = Mock()
    response.json.return_value = {"choices": [{"message": {
        "content": json.dumps(facts()), "reasoning_content": "ignore this invalid JSON",
    }}], "usage": {"total_tokens": 42}}
    post = Mock(return_value=response)
    monkeypatch.setattr(analysis.httpx, "post", post)
    content, tokens = analysis.chat({"title": "Engineer"}, "Python", settings)
    assert json.loads(content) == facts() and tokens == 42
    assert post.call_args.args == ("https://example.invalid/v1/chat/completions",)
    assert post.call_args.kwargs["follow_redirects"] is False
    payload = post.call_args.kwargs["json"]
    assert payload["model"] == "fake"
    assert "NEVER programming languages" in payload["messages"][0]["content"]
    assert json.loads(payload["messages"][1]["content"])["profile"] == "Python"


def test_description_html_removal_and_limit():
    job = analysis.job_input({"title": "Engineer", "company": "Acme", "locations": None,
                              "description": "<p>" + "x" * 9000 + "</p>"})
    assert job["description"] == "x" * 8000 and job["locations"] == []


@pytest.fixture
def analysis_db(monkeypatch):
    if os.environ.get("JAGENT_TEST_POSTGRES") != "1":
        pytest.skip("Set JAGENT_TEST_POSTGRES=1 to test analysis in temporary tables")
    monkeypatch.setattr(analysis.time, "sleep", Mock())
    with connect() as connection:
        connection.execute("""
            CREATE TEMP TABLE profile (id int, text text, filters jsonb);
            CREATE TEMP TABLE profile_sections (profile_id int, name text, text text);
            CREATE TEMP TABLE postings (id int PRIMARY KEY, title text, company text,
                                       locations text[], description text);
            CREATE TEMP TABLE matches (posting_id int, profile_id int, queued bool,
                similarity float, matched_section text, explanation text);
        """)
        schema = (Path(__file__).resolve().parent.parent / "schema.sql").read_text()
        statement = schema[schema.index("CREATE TABLE IF NOT EXISTS posting_analysis"):
                           schema.index("ALTER TABLE matches ADD COLUMN IF NOT EXISTS explanation")]
        connection.execute(statement.replace("CREATE TABLE IF NOT EXISTS", "CREATE TEMP TABLE"))
        connection.execute("""
            INSERT INTO profile VALUES (1,'Sample profile','{}'),
                (2,'## Engineering\nPython skills\n## Languages\nEnglish Italian Albanian','{}');
            INSERT INTO profile_sections VALUES (1,'Engineering','Old skills'),
                                                 (2,'Engineering','Python skills');
            INSERT INTO postings VALUES
                (1,'Engineer','Acme','{Albania}',
                 '<p>mid Python English full time 100-200 EUR/year</p>'),
                (2,'Not queued','Acme','{}','description'),
                (3,'Old profile only','Acme','{}','description');
            INSERT INTO matches VALUES (1,2,true,.8,'Engineering',NULL),
                (2,2,false,.7,'Engineering',NULL), (3,1,true,.9,'Engineering',NULL);
        """)
        connection.commit()
        monkeypatch.setattr(analysis, "connect", lambda: nullcontext(connection))
        yield connection


def test_store_facts_explanation_tokens_and_cache(analysis_db, capsys):
    fake = Mock(return_value=(json.dumps(facts()), 42))
    settings = {"LLM_MODEL": "fake"}
    assert analysis.analyze(fake, settings) == {"analyzed": 1, "failures": 0, "tokens": 42}
    assert fake.call_args.args[1] == "## Engineering\nPython skills\n## Languages\nEnglish Italian Albanian"
    assert fake.call_args.args[0]["description"] == "mid Python English full time 100-200 EUR/year"
    row = analysis_db.execute(
        "SELECT seniority,required_languages,employment_types,salary,evidence,model FROM posting_analysis"
    ).fetchone()
    assert row == ("mid", ["English"], ["full_time"], facts()["salary"], facts()["evidence"], "fake")
    assert analysis_db.execute("SELECT explanation FROM matches WHERE posting_id=1").fetchone()[0] == facts()["explanation"]
    output = capsys.readouterr().out
    assert "Analysed=1 failures=0 tokens=42" in output and '"title": "Engineer"' in output
    assert analysis.analyze(fake, settings)["analyzed"] == 0
    assert fake.call_count == 1
    assert analysis.analyze(fake, {"LLM_MODEL": "new-model"})["analyzed"] == 1
    assert analysis_db.execute("SELECT count(*) FROM posting_analysis").fetchone()[0] == 1


def test_invalid_output_retry_and_next_run(analysis_db, capsys):
    fake = Mock(side_effect=[("not JSON", 3), (json.dumps(facts(seniority="director")), 5)])
    settings = {"LLM_MODEL": "fake"}
    assert analysis.analyze(fake, settings) == {"analyzed": 0, "failures": 1, "tokens": 8}
    assert analysis_db.execute("SELECT count(*) FROM posting_analysis").fetchone()[0] == 0
    output = capsys.readouterr().out
    assert 'remaining errors by type: {"validation:literal_error": 1}' in output
    assert analysis.analyze(lambda *_: (json.dumps(facts()), 7), settings)["analyzed"] == 1


def test_fabricated_evidence_retries_then_validates(analysis_db):
    fake = Mock(side_effect=[(json.dumps(facts(evidence={**facts()["evidence"], "seniority": "invented"})), 4),
                            (json.dumps(facts()), 6)])
    assert analysis.analyze(fake, {"LLM_MODEL": "fake"}) == {"analyzed": 1, "failures": 0, "tokens": 10}


def test_provider_errors_do_not_print_key(analysis_db, capsys):
    fake = Mock(side_effect=analysis.httpx.ReadTimeout("fake-api-key"))
    assert analysis.analyze(fake, {"LLM_MODEL": "fake"})["failures"] == 1
    assert "fake-api-key" not in capsys.readouterr().out


@pytest.mark.parametrize("analyzed,failures,exit_code", [
    (82, 1, 0), (8, 2, 1), (0, 3, 1), (9, 1, 0), (89, 11, 1),
    (0, 0, 0), (83, 0, 0),
])
def test_analyze_cli(monkeypatch, capsys, analyzed, failures, exit_code):
    monkeypatch.setattr(cli, "analyze", lambda: {"analyzed": analyzed, "failures": failures})
    monkeypatch.setattr("sys.argv", ["jagent", "analyze"])
    assert cli.main() == exit_code
    assert capsys.readouterr().out == (f"warning: {failures} retried next run\n" if failures else "")


@pytest.mark.parametrize("fence", ["```json", "```", "```JSON"])
def test_strip_json_fences(fence):
    assert analysis.parse_analysis(fence + "\n" + json.dumps(facts()) + "\n```").seniority == "mid"


def test_rate_limit_waits_before_retry(analysis_db, monkeypatch):
    response = analysis.httpx.Response(429, headers={"retry-after": "12"},
        request=analysis.httpx.Request("POST", "https://example.invalid/v1/chat/completions"))
    error = analysis.httpx.HTTPStatusError("fake-api-key", request=response.request, response=response)
    fake = Mock(side_effect=[error, (json.dumps(facts()), 7)])
    sleep = Mock()
    monkeypatch.setattr(analysis.time, "sleep", sleep)
    assert analysis.analyze(fake, {"LLM_MODEL": "fake"})["failures"] == 0
    assert [call.args for call in sleep.call_args_list] == [(12,), (1.5,)]


def test_verbatim_quote_whitespace(analysis_db):
    fake = Mock(return_value=(json.dumps(facts(evidence={**facts()["evidence"],
                                                       "employment_types": "full\n time"})), 7))
    assert analysis.analyze(fake, {"LLM_MODEL": "fake"})["analyzed"] == 1


def test_real_chat_receives_retry_feedback_and_whole_profile(analysis_db, monkeypatch):
    fake = Mock(side_effect=[("invalid JSON", 2), (json.dumps(facts()), 7)])
    monkeypatch.setattr(analysis, "chat", fake)
    assert analysis.analyze(settings={"LLM_MODEL": "fake"})["analyzed"] == 1
    args = fake.call_args.args
    assert "## Engineering" in args[1] and "## Languages" in args[1]
    assert "validation:json_invalid" in args[3] and "contiguous verbatim" in args[3]


def test_remaining_errors_grouped_by_type(analysis_db, capsys):
    analysis_db.execute("UPDATE matches SET queued=true WHERE posting_id=2")
    response = analysis.httpx.Response(403, request=analysis.httpx.Request(
        "POST", "https://example.invalid/v1/chat/completions"))
    error = analysis.httpx.HTTPStatusError("fake-api-key", request=response.request, response=response)
    fake = Mock(side_effect=[error, error, ("not JSON", 2), ("not JSON", 2)])
    assert analysis.analyze(fake, {"LLM_MODEL": "fake"})["failures"] == 2
    output = capsys.readouterr().out
    assert 'remaining errors by type: {"http_403": 1, "validation:json_invalid": 1}' in output
    assert "Failure rate: 100.0%" in output and "fake-api-key" not in output


@pytest.mark.parametrize("stage", ["request", "backoff", "pacing"])
def test_keyboard_interrupt_propagates_from_retry_loop(analysis_db, monkeypatch, stage):
    if stage == "backoff":
        response = analysis.httpx.Response(429, request=analysis.httpx.Request(
            "POST", "https://example.invalid/v1/chat/completions"))
        first = analysis.httpx.HTTPStatusError("rate limited", request=response.request, response=response)
    elif stage == "pacing":
        first = ("invalid JSON", 2)
    else:
        first = KeyboardInterrupt()
    fake = Mock(side_effect=[first, AssertionError("Must not retry after interruption")])
    monkeypatch.setattr(analysis.time, "sleep", Mock(side_effect=KeyboardInterrupt))
    with pytest.raises(KeyboardInterrupt):
        analysis.analyze(fake, {"LLM_MODEL": "fake"})
    assert fake.call_count == 1


def test_unexpected_errors_propagate(analysis_db):
    with pytest.raises(RuntimeError, match="unexpected bug"):
        analysis.analyze(Mock(side_effect=RuntimeError("unexpected bug")), {"LLM_MODEL": "fake"})


def test_pause_between_postings(analysis_db):
    analysis_db.execute("UPDATE matches SET queued=true WHERE posting_id=2")
    unstated = facts(seniority="unknown", required_languages=[], employment_types=None,
                    salary=None, evidence={})
    fake = Mock(return_value=(json.dumps(unstated), 7))
    assert analysis.analyze(fake, {"LLM_MODEL": "fake"})["analyzed"] == 2
    analysis.time.sleep.assert_called_once_with(1.5)
