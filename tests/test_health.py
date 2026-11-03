# Health tests; rows represent latest runs and their seven-day fetched medians.
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
import json
from unittest.mock import Mock

import pytest

from jagent import cli, health


@pytest.mark.parametrize("status,fetched,median,error,expected", [
    ("ok", 100, 100, None, []),
    ("ok", 30, 90, None, []),
    ("ok", 29, 90, None, ["sample: fetched=29 below one third of 7-day median=90"]),
    ("ok", 0, 0, None, ["sample: fetched=0"]),
    ("error", 100, 100, "HTTP 404", ["sample: status=error (HTTP 404)"]),
    ("ok", 5, None, None, []),
])
def test_health_rules(monkeypatch, status, fetched, median, error, expected):
    connection = Mock()
    connection.execute.return_value.fetchall.return_value = [
        ("sample", status, fetched, error, median, False),
    ]
    monkeypatch.setattr(health, "connect", lambda: nullcontext(connection))
    assert health.check_health() == expected


@pytest.mark.parametrize("problems,exit_code", [([], 0), (["sample: fetched=0"], 1)])
def test_health_cli(monkeypatch, capsys, problems, exit_code):
    monkeypatch.setattr(cli, "duapune_freshness", lambda: "Fresh: fixture")
    monkeypatch.setattr("sys.argv", ["jagent", "health"])
    monkeypatch.setattr(cli, "check_health", lambda: problems)
    assert cli.main() == exit_code
    assert capsys.readouterr().out == "".join(problem + "\n" for problem in problems)


@pytest.mark.parametrize("error", ["Import older than 36 hours", "Import file missing"])
@pytest.mark.parametrize("server_failed", [False, True])
def test_import_warning_does_not_hide_server_failure(monkeypatch, capsys, error, server_failed):
    monkeypatch.setattr(cli, "duapune_freshness", lambda: "Fresh: fixture")
    connection = Mock()
    rows = [("duapune", "error", 0, error, 0, True)]
    if server_failed:
        rows.append(("remotive", "error", 100, "HTTP 503", 100, False))
    connection.execute.return_value.fetchall.return_value = rows
    monkeypatch.setattr(health, "connect", lambda: nullcontext(connection))
    monkeypatch.setattr("sys.argv", ["jagent", "health"])

    assert cli.main() == int(server_failed)
    warning = (f"duapune: status=error ({error}); "
               "stale (latest run older than 36 hours); fetched=0")
    expected = f"warning: {warning}\n"
    if server_failed:
        expected += "remotive: status=error (HTTP 503)\n"
    assert capsys.readouterr().out == expected
    # Keep the underlying health message available to dashboard banner consumers.
    assert health.check_health()[0] == warning


def test_ats_zero_yield_is_healthy_and_errors_are_summarized(monkeypatch):
    connection = Mock()
    connection.execute.return_value.fetchall.return_value = [
        ("ats:ashby:acme", "error", 0, "HTTP 404", 0, False),
        ("ats:greenhouse:stripe", "ok", 0, None, 100, True),
        ("ats:lever:notion", "error", 0, "HTTP 500", 0, False),
    ]
    monkeypatch.setattr(health, "connect", lambda: nullcontext(connection))
    assert health.check_health() == [
        "ats: 2 of 3 boards failed (ashby/acme, lever/notion)"
    ]


@pytest.mark.parametrize("source", ["himalayas", "djinni"])
@pytest.mark.parametrize("fetched", [0, 1])
def test_incremental_sources_ignore_yield_rules(monkeypatch, source, fetched):
    connection = Mock()
    connection.execute.return_value.fetchall.return_value = [(source, "ok", fetched, None, 100, False)]
    monkeypatch.setattr(health, "connect", lambda: nullcontext(connection))
    assert health.check_health() == []


@pytest.mark.parametrize("source", ["himalayas", "djinni"])
def test_incremental_errors_are_problems(monkeypatch, source):
    connection = Mock()
    connection.execute.return_value.fetchall.return_value = [(source, "error", 0, "HTTP 404", 100, False)]
    monkeypatch.setattr(health, "connect", lambda: nullcontext(connection))
    assert health.check_health() == [f"{source}: status=error (HTTP 404)"]


@pytest.mark.parametrize("source", ["sample", "himalayas", "djinni"])
def test_non_ats_staleness(monkeypatch, source):
    connection = Mock()
    connection.execute.return_value.fetchall.return_value = [(source, "ok", 100, None, 100, True)]
    monkeypatch.setattr(health, "connect", lambda: nullcontext(connection))
    assert health.check_health() == [f"{source}: stale (latest run older than 36 hours)"]


@pytest.mark.parametrize("age,status", [(1, "Fresh"), (37, "Stale")])
def test_duapune_import_freshness(monkeypatch, tmp_path, age, status):
    path = tmp_path / "duapune.json"
    collected_at = datetime.now(UTC) - timedelta(hours=age)
    path.write_text(json.dumps({"collected_at": collected_at.isoformat()}))
    monkeypatch.setattr(health.duapune, "IMPORT_PATH", path)
    assert health.duapune_freshness() == (
        f"{status}: collected at {collected_at:%Y-%m-%d %H:%M:%S} UTC"
    )


@pytest.mark.parametrize("contents", ['{}', '{', '{"collected_at":"2026-10-27T10:00:00"}'])
def test_invalid_duapune_import_freshness(monkeypatch, tmp_path, contents):
    path = tmp_path / "duapune.json"
    path.write_text(contents)
    monkeypatch.setattr(health.duapune, "IMPORT_PATH", path)
    assert health.duapune_freshness().startswith("Invalid")


@pytest.mark.parametrize('age,expected', [(36 * 3600, 'Fresh'), (36 * 3600 + 1, 'Stale'), (-1, 'Invalid')])
def test_import_age_boundaries_share_adapter_policy(monkeypatch, tmp_path, age, expected):
    now = datetime(2026, 11, 3, 12, tzinfo=UTC)
    path = tmp_path / 'import.json'
    path.write_text(json.dumps({'collected_at': (now - timedelta(seconds=age)).isoformat()}))
    monkeypatch.setattr(health.duapune, 'IMPORT_PATH', path)
    assert health.duapune_freshness(now).startswith(expected)


def test_stale_import_is_visible_even_when_last_source_run_succeeded(monkeypatch, tmp_path):
    path = tmp_path / 'import.json'
    path.write_text(json.dumps({'collected_at': (datetime.now(UTC) - timedelta(hours=37)).isoformat()}))
    monkeypatch.setattr(health.duapune, 'IMPORT_PATH', path)
    problems = health.operational_problems([], None, health.duapune_freshness())
    assert len(problems) == 1 and problems[0].startswith('Duapune import: Stale:')


def test_health_cli_warns_about_import_age_before_next_collection(monkeypatch, capsys):
    monkeypatch.setattr('sys.argv', ['jagent', 'health'])
    monkeypatch.setattr(cli, 'check_health', lambda: [])
    monkeypatch.setattr(cli, 'duapune_freshness', lambda: 'Stale: collected at 2026-11-02 04:31:22 UTC')
    assert cli.main() == 0
    assert capsys.readouterr().out == 'warning: Duapune import: Stale: collected at 2026-11-02 04:31:22 UTC\n'


def test_unreadable_import_is_not_misreported_as_invalid_timestamp(monkeypatch):
    monkeypatch.setattr(health.duapune, 'IMPORT_PATH', Mock(read_text=Mock(side_effect=PermissionError)))
    assert health.duapune_freshness() == 'Unreadable import file'
