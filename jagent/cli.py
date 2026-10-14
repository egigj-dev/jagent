# Command-line entry point; schema_path locates the SQL used by init-db.
import argparse
from pathlib import Path

from jagent.db import connect
from jagent.analysis import analyze
from jagent.health import check_health
from jagent.filters import filter_report
from jagent.profile import set_profile
from jagent.matching import match
from jagent.runner import SOURCES, backfill_dedupe, run


MAX_FAILURE_RATE = 0.10


def retry_exit_code(failures, attempted):
    if not failures:
        return 0
    print(f"warning: {failures} retried next run")
    return int(failures == attempted or failures / attempted > MAX_FAILURE_RATE)


def main():
    parser = argparse.ArgumentParser(prog="jagent")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db", help="Create the database tables if absent")
    commands.add_parser("health", help="Check the latest source runs for problems")
    commands.add_parser("filter-report", help="Report active postings passing profile filters")
    commands.add_parser("match", help="Embed and rank postings against the active profile")
    commands.add_parser("analyze", help="Extract job facts and explain queued matches")
    commands.add_parser("serve", help="Serve the review dashboard on 127.0.0.1:8000")
    profile_parser = commands.add_parser("profile", help="Store profile versions")
    profile_commands = profile_parser.add_subparsers(dest="profile_command", required=True)
    profile_set = profile_commands.add_parser("set", help="Store a new active profile version")
    profile_set.add_argument("text_path")
    profile_set.add_argument("filters_path")
    run_parser = commands.add_parser("run", help="Fetch and store job postings")
    run_parser.add_argument("--source", choices=sorted(SOURCES))
    args = parser.parse_args()
    if args.command == "serve":
        import uvicorn
        uvicorn.run("jagent.dashboard:app", host="127.0.0.1", port=8000)
        return 0
    if args.command == "analyze":
        try:
            result = analyze()
        except ValueError as error:
            print(str(error))
            return 1
        return retry_exit_code(result["failures"], result["analyzed"] + result["failures"])
    if args.command == "match":
        try:
            result = match()
        except ValueError as error:
            print(str(error))
            return 1
        return retry_exit_code(result["batches_skipped"], result["batches_attempted"])
    if args.command == "profile":
        profile_id = set_profile(args.text_path, args.filters_path)
        print(f"Profile version {profile_id} is active.")
        return 0
    if args.command == "filter-report":
        filter_report()
        return 0
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
