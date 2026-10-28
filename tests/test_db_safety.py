# Database safety tests; fake connections verify rejection before fixture SQL runs.
from pathlib import Path
from unittest.mock import Mock

import pytest

from jagent import db
from tests.conftest import connect_test_database


def test_missing_test_url_never_uses_application_settings(monkeypatch):
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://jagent@127.0.0.1:5434/jagent")
    read = Mock(side_effect=AssertionError("Database tests must not read .env"))
    connect = Mock(side_effect=AssertionError("Database tests must not connect"))
    monkeypatch.setattr(Path, "read_text", read)
    monkeypatch.setattr("psycopg.connect", connect)
    with pytest.raises(ValueError, match="Set TEST_DATABASE_URL"):
        db.connect()
    read.assert_not_called()
    connect.assert_not_called()


@pytest.mark.parametrize("url", [
    "postgresql://jagent@127.0.0.1:5434/jagent",
    "dbname=jagent host=127.0.0.1 port=5434",
    "host=127.0.0.1 port=5434",
    "postgresql://jagent@127.0.0.1:5434/jagent_test?dbname=jagent",
])
def test_unsafe_database_name_rejected_before_connecting(monkeypatch, url):
    monkeypatch.setenv("TEST_DATABASE_URL", url)
    connect = Mock()
    monkeypatch.setattr("psycopg.connect", connect)
    with pytest.raises(ValueError, match="database name must end in '_test'"):
        connect_test_database()
    connect.assert_not_called()


@pytest.mark.parametrize("database_name", ["jagent", "jagent_test"])
def test_connected_database_name_checked_before_returning(monkeypatch, database_name):
    url = "postgresql://jagent@127.0.0.1:5434/jagent_test"
    monkeypatch.setenv("TEST_DATABASE_URL", url)
    connection = Mock()
    connection.execute.return_value.fetchone.return_value = (database_name,)
    connect = Mock(return_value=connection)
    monkeypatch.setattr("psycopg.connect", connect)
    if database_name == "jagent_test":
        assert connect_test_database() is connection
        connection.rollback.assert_called_once_with()
        connection.close.assert_not_called()
    else:
        with pytest.raises(ValueError, match="connected database name must end in '_test'"):
            connect_test_database()
        connection.close.assert_called_once_with()
    connect.assert_called_once_with(url, options="-c timezone=UTC")
    connection.execute.assert_called_once_with("SELECT current_database()")
