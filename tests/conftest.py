# Test database isolation; TEST_DATABASE_URL is the only connection setting used.
import os

import psycopg
from psycopg.conninfo import conninfo_to_dict
import pytest

from jagent import db


def connect_test_database():
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        raise ValueError("Set TEST_DATABASE_URL to a database whose name ends in '_test'")
    database_name = conninfo_to_dict(database_url).get("dbname", "")
    if not database_name.endswith("_test"):
        raise ValueError("Refusing database tests: TEST_DATABASE_URL database name must end in '_test'")
    connection = psycopg.connect(database_url, options="-c timezone=UTC")
    try:
        database_name = connection.execute("SELECT current_database()").fetchone()[0]
        if not database_name.endswith("_test"):
            raise ValueError("Refusing database tests: connected database name must end in '_test'")
        connection.rollback()
    except BaseException:
        connection.close()
        raise
    return connection


def pytest_configure(config):
    # Replace the connector before collection imports it into application modules.
    patch = pytest.MonkeyPatch()
    patch.setattr(db, "connect", connect_test_database)
    config.add_cleanup(patch.undo)
