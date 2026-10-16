<!-- Public project guide; commands use the current checkout and local configuration. -->
# jagent

## Summary

A personal job-search pipeline that collects postings, ranks them against a profile,
and explains a shortlist in a local review dashboard. Python 3.12, PostgreSQL and
pgvector; plain functions and SQL.

## Screenshot placeholder

TODO: Add a dashboard screenshot using anonymized sample data.

## Problem

Job boards repeat the same roles across sites and mix useful opportunities with
irrelevant locations and titles. Reviewing each listing by hand takes time and
makes it hard to track what has already been considered or applied to.

## How it works

Source adapters collect APIs, RSS, HTML and imported files into a shared postings
table. Normalized company and title identify duplicates; other URLs and locations
are merged. Location and title rules narrow the candidates. Embeddings compare
postings with individual profile sections, keeping the best section score. A
percentile cutoff and similarity floor select the queue. One structured LLM step
extracts facts and explains matches, with evidence checked against the source.
The dashboard supports review, saving jobs and tracking applications.

See the [architecture and Mermaid diagrams](docs/architecture.md), or the PlantUML
[components](docs/components.puml), [database](docs/database-entities.puml),
[daily run](docs/daily-run.puml) and [posting lifecycle](docs/posting-lifecycle.puml).

## Key design decisions

The pipeline has deterministic collectors and ranking, with an LLM at the analysis
step. PostgreSQL is the boundary between collection and judgment. See
[the decisions and alternatives](docs/decisions.md).

## Results

- TODO: Collection volume and source coverage.
- TODO: Shortlist relevance and examples.
- TODO: Time saved, API costs and application outcomes.

## Setup

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

Tests use temporary tables in the configured database (including pgvector):

```bash
JAGENT_TEST_POSTGRES=1 uv run pytest
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

## Limitations

Source formats and availability can change. Bot-protected sources require an
external collector on a home connection; transfer its output to
`imports/duapune.json`. That collector is outside this repository. Imports older
than 36 hours raise a health warning. ATS coverage depends on discovered boards.
Embedding similarity and LLM explanations need human review. The dashboard is
intended for local access; use an SSH tunnel for a remote server. Private SQL exports are ignored; the public `schema.sql` contains only table and
index definitions.

## Roadmap

- TODO: Document measured relevance and operating costs.
- TODO: Add an anonymized dashboard screenshot.
- TODO: Review source coverage and parser maintenance priorities.
