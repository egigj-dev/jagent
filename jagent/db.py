# Database connection; DATABASE_URL comes from the environment or the project .env.
import os
from pathlib import Path

import psycopg


def connect():
    database_url = os.environ.get("DATABASE_URL")
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if database_url is None and env_path.exists():
        for line in env_path.read_text().splitlines():
            key, separator, value = line.partition("=")
            if separator and key.strip() == "DATABASE_URL":
                database_url = value.strip().strip("\"'")
                break
    if not database_url:
        raise ValueError("Set DATABASE_URL in the environment or project .env")
    return psycopg.connect(database_url, options="-c timezone=UTC")
