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
