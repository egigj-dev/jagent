<!-- Setup guide; commands configure local files, database, dashboard and optional systemd services. -->
# Setup and operation

Install Python 3.12+, uv, Docker and Docker Compose. From your checkout:

```bash
uv sync --group dev
cp .env.example .env
cp profile.example.md profile.md
cp filters.example.json filters.json
```

Edit `.env`, choosing a database password and matching `DATABASE_URL`. Set the
embedding and LLM API keys, models and OpenAI-compatible `/v1` base URLs. Use the same embedding model for profiles and postings. Profile text and job descriptions are sent
to the configured API providers. Edit the profile and filters for your own search.
These local files and `imports/` are ignored by Git.

```bash
docker compose up -d db
uv run jagent init-db
uv run jagent profile set profile.md filters.json
uv run jagent run
uv run jagent match
uv run jagent analyze
uv run jagent health
uv run jagent serve
```

Open <http://127.0.0.1:8000/>. **Profile** edits your background and goals;
`## Section` headings separate areas of experience. **Preferences** controls
location and excluded-title rules. **Opportunities** supports searching, filtering,
saving and marking jobs as applied. Profile changes take effect on the next run.
PostgreSQL binds to `127.0.0.1:5434`; the dashboard binds to `127.0.0.1:8000`.

Create a separate local database for tests and enable pgvector:

```bash
docker exec jagent-db-1 createdb -U jagent jagent_test
docker exec jagent-db-1 psql -U jagent -d jagent_test -c 'CREATE EXTENSION IF NOT EXISTS vector'
```

Tests use temporary tables in that database. Set `TEST_DATABASE_URL` explicitly
with your local database password; tests never read `DATABASE_URL` or `.env`.
Both the configured and connected database names must end in `_test`:

```bash
TEST_DATABASE_URL=postgresql://jagent:change-me@127.0.0.1:5434/jagent_test JAGENT_TEST_POSTGRES=1 uv run pytest
```

### Optional systemd deployment

The service files are templates. Run these commands as your regular user from the
checkout to substitute your current username, home and project directory before
installing the system units. Keep the checkout path free of spaces and sed delimiter
characters. uv is expected at `$HOME/.local/bin/uv`.

```bash
for unit in jagent.service jagent-web.service; do
    sed -e "s|@USER@|$(id -un)|g" -e "s|@HOME@|$HOME|g" \
        -e "s|@PROJECT_DIR@|$PWD|g" "deploy/$unit" | sudo tee "/etc/systemd/system/$unit" >/dev/null
done
sudo install -m 644 deploy/jagent.timer /etc/systemd/system/jagent.timer
sudo systemctl daemon-reload
sudo systemctl enable jagent.service
sudo systemctl enable --now jagent.timer jagent-web.service
```

The pipeline runs at 07:00 Europe/Tirane and catches missed runs after reboot.
It runs `run`, `match`, `analyze`, then `health`, continuing after failures and
returning failure if any step fails. Logs use UTC. Check service logs with
`sudo journalctl -u jagent.service -u jagent-web.service -n 100 --no-pager`
and the schedule with `sudo systemctl list-timers jagent.timer --all`.
Run immediately with `sudo systemctl start jagent.service`.


## Laptop imports

Bot-protected sources are collected from a home connection by an external
collector. Transfer its output to `imports/duapune.json`. Missing or stale Duapune
imports appear as warnings in `jagent health` and in the dashboard banner; they
do not make health exit with failure. Other source health failures still do.


## Source coverage

Workday has no adapter and is not called by the runner. Company boards currently
support Greenhouse, Lever, Ashby and SmartRecruiters; these run after the named
sources. The dashboard's **Health** page at `/health` shows the latest run for each
source and the freshness of the Duapune import.

CI runs the complete suite with `JAGENT_TEST_POSTGRES=1` against a temporary
pgvector/PostgreSQL 16 service with database `jagent_test`.
Local tests remain opt-in for database access;
`uv run pytest` runs without that gate. Filter tests use explicit search terms
and do not read personal configuration.
