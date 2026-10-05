# Command-line entry point; schema_path locates the SQL used by init-db.
import argparse
from pathlib import Path

from jagent.db import connect
from jagent.health import check_health
from jagent.runner import SOURCES, backfill_dedupe, run


def main():
    parser = argparse.ArgumentParser(prog="jagent")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db", help="Create the database tables if absent")
    commands.add_parser("health", help="Check the latest source runs for problems")
    run_parser = commands.add_parser("run", help="Fetch and store job postings")
    run_parser.add_argument("--source", choices=sorted(SOURCES))
    args = parser.parse_args()
    if args.command == "health":
        problems = check_health()
        for problem in problems:
            print(problem)
        return int(bool(problems))
    if args.command == "run":
        results = run(args.source)
        for result in results:
            print(f"{result['source']}: status={result['status']} "
                  f"fetched={result['fetched']} new={result['new']}")
            if result["error"]:
                print(result["error"])
        return int(any(result["status"] == "error" for result in results))
    schema_path = Path(__file__).resolve().parent.parent / "schema.sql"
    with connect() as connection:
        connection.execute(schema_path.read_text())
        backfill_dedupe(connection)
    print("Database initialized.")
