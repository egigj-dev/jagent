# Profile versions; text_path and filters_path supply user files, and the greatest id is active.
import json
from pathlib import Path

from psycopg.types.json import Jsonb

from jagent.db import connect


def split_sections(text):
    sections = []
    name = None
    lines = []
    for line in text.splitlines():
        if line.startswith("## "):
            if name is not None:
                sections.append((name, "\n".join(lines).strip()))
            name = line[3:].strip()
            lines = []
        elif name is not None:
            lines.append(line)
    if name is not None:
        sections.append((name, "\n".join(lines).strip()))
    return sections


def set_profile(text_path, filters_path):
    text = Path(text_path).read_text()
    filters = json.loads(Path(filters_path).read_text())
    with connect() as connection:
        profile_id = connection.execute(
            "INSERT INTO profile (text, filters) VALUES (%s, %s) RETURNING id",
            (text, Jsonb(filters)),
        ).fetchone()[0]
        for name, section_text in split_sections(text):
            connection.execute(
                "INSERT INTO profile_sections (profile_id, name, text) VALUES (%s, %s, %s)",
                (profile_id, name, section_text),
            )
        return profile_id


def active_profile(connection):
    return connection.execute(
        "SELECT id, text, filters FROM profile ORDER BY id DESC LIMIT 1"
    ).fetchone()
