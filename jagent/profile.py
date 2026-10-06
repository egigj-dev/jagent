# Profile versions; text_path and filters_path supply user files, and the greatest id is active.
import json
from pathlib import Path

from psycopg.types.json import Jsonb

from jagent.db import connect


def set_profile(text_path, filters_path):
    text = Path(text_path).read_text()
    filters = json.loads(Path(filters_path).read_text())
    with connect() as connection:
        return connection.execute(
            "INSERT INTO profile (text, filters) VALUES (%s, %s) RETURNING id",
            (text, Jsonb(filters)),
        ).fetchone()[0]


def active_profile(connection):
    return connection.execute(
        "SELECT id, text, filters FROM profile ORDER BY id DESC LIMIT 1"
    ).fetchone()
