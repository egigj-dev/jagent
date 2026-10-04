# Command-line entry point; schema_path locates the SQL used by init-db.
import argparse
from pathlib import Path

from jagent.db import connect


def main():
    parser = argparse.ArgumentParser(prog="jagent")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db", help="Create the database tables if absent")
    parser.parse_args()
    schema_path = Path(__file__).resolve().parent.parent / "schema.sql"
    with connect() as connection:
        connection.execute(schema_path.read_text())
    print("Database initialized.")
