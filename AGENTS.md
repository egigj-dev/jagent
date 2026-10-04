# jagent
Personal job-search pipeline. Python 3.12, uv, Postgres with pgvector in Docker.

## Rules
- Keep code simple enough for one person to maintain: plain functions, no classes unless needed.
- Libraries: httpx, beautifulsoup4, psycopg (v3), pydantic, pytest. Ask before adding any other.
- Plain SQL in schema.sql. No ORM, no migration tool.
- Every new file starts with a comment saying what it does and describing its main variables.
- Never touch the Postgres on port 5433; it belongs to another project.
- Bind every service and container port to 127.0.0.1.
- Store all timestamps in UTC.
- Do only the current task. No extra features or abstractions.
- When finished, report each "Done when" check with the exact command you ran and its output.

## Layout
jagent/cli.py, db.py, models.py, runner.py, sources/<one file per source>.py
tests/ (with tests/fixtures/ for saved sample responses), schema.sql, docker-compose.yml
