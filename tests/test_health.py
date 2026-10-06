# Health tests; rows represent latest runs and their seven-day fetched medians.
from contextlib import nullcontext
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
        ("sample", status, fetched, error, median),
    ]
    monkeypatch.setattr(health, "connect", lambda: nullcontext(connection))
    assert health.check_health() == expected


@pytest.mark.parametrize("problems,exit_code", [([], 0), (["sample: fetched=0"], 1)])
def test_health_cli(monkeypatch, capsys, problems, exit_code):
    monkeypatch.setattr("sys.argv", ["jagent", "health"])
    monkeypatch.setattr(cli, "check_health", lambda: problems)
    assert cli.main() == exit_code
    assert capsys.readouterr().out == "".join(problem + "\n" for problem in problems)


def test_ats_zero_yield_is_healthy_and_errors_are_summarized(monkeypatch):
    connection = Mock()
    connection.execute.return_value.fetchall.return_value = [
        ("ats:ashby:acme", "error", 0, "HTTP 404", 0),
        ("ats:greenhouse:stripe", "ok", 0, None, 0),
        ("ats:lever:notion", "error", 0, "HTTP 500", 0),
    ]
    monkeypatch.setattr(health, "connect", lambda: nullcontext(connection))
    assert health.check_health() == [
        "ats: 2 of 3 boards failed (ashby/acme, lever/notion)"
    ]
