<!-- Atlas × Terminal implementation record; commands reproduce validation and artifact paths identify fixture-only screenshots. -->
# Atlas × Terminal UI

Implemented on `feat/atlas-terminal-ui`. No dependencies were introduced.

Warm paper and a carbon navigation rail frame an opportunity index and an intelligence reading panel. Editorial serif headings, system sans body text, and monospace annotations distinguish reading from metadata. Green represents profile connections and saved state; copper marks direction, links and focus. All fonts and assets work locally without a CDN.

The index exposes company, title, location, remote status, posting date when present, source, profile similarity and saved state. Select a row to read its stored assessment, matched profile section, extracted requirements and original evidence quotes. Quick Save and the decision form use existing review persistence. Advanced filters expose every existing view option, including language, seniority and contract exclusions. Saved remains a filtered view of the queue. Applied uses expandable application records.

On small screens the index leads into a separate detail view with a back control. With keyboard focus in the index, Up/Down and Home/End select rows; Enter focuses the brief. `/` focuses search outside text controls. Escape returns to the mobile index. Normal links and server form submissions remain available without JavaScript. Forms expose pending, success and failure feedback, and retain notes after a failed request.

Profile retains its original text model and optional `##` headings, with search preferences in a disclosure. Preferences groups locations, exclusions and local discovery. Source health remains accessible as secondary operational navigation.

## Main files

- `jagent/static/dashboard.css`: shared semantic tokens, typography, controls, layout and responsive states.
- `jagent/static/workspace.js`: progressive selection, keyboard navigation, review submission and feedback.
- `jagent/templates/base.html`, `queue.html`, `queue_content.html`, `posting.html`: workspace composition, filters, index, analysis and evidence.
- `jagent/templates/profile.html`, `filters.html`, `applied.html`: consistent secondary screens. Existing Health templates inherit the shared system.
- `jagent/dashboard.py`: reads existing requirement evidence and matched profile-section text; normalizes browser form line endings so an unchanged profile retains cached matches. No ranking or schema changes.
- `tests/test_dashboard.py`, `tests/workspace_browser.py`: evidence/filter assertions, profile regression and optional browser acceptance checks.

## Definition-of-done checks

The test runner used below is the existing workspace helper `/tmp/jagent-run-tests.py`. It reads local connection settings without printing credentials, selects only `jagent_test`, requires port 5434 and enables the existing database tests. Tests use temporary tables and prohibit provider calls. Port 5433 was not accessed.

**Existing interactions, persistence and automated regressions:**

```sh
JAGENT_BROWSER_PYTHON=/home/egigj/.cache/uv/archive-v0/n169s7cegO4KK6xL/bin/python .venv/bin/python /tmp/jagent-run-tests.py -q
```

Output: `388 passed, 1 warning in 20.38s`.

The warning is the existing Starlette TestClient deprecation of its httpx integration. No dependency was changed to suppress it.

**Desktop/mobile navigation, comprehension, rapid review and visual consistency:**

```sh
JAGENT_BROWSER_PYTHON=/home/egigj/.cache/uv/archive-v0/n169s7cegO4KK6xL/bin/python .venv/bin/python /tmp/jagent-run-tests.py tests/test_dashboard.py::test_workspace_browser -q -s
```

Browser acceptance output:

```text
PASS: selection, keyboard, search, filters, responsive layouts (320–1440px), error recovery, Save/Skip/Apply persistence, profile save, preferences save, no-JavaScript fallback; no browser errors.
Screenshots: /tmp/jagent-atlas-review
1 passed, 1 warning in 6.22s
```

Screenshots were inspected for Opportunities desktop, mobile index and mobile detail, Profile and Preferences. The browser also checks Applied and Health at desktop and mobile widths. Screenshots use isolated test fixtures; none are embedded as production content. Layout assertions cover 320, 390, 768, 1024 and 1440px; secondary screens cover 320, 390 and 1440px. This is a Chromium check, not a full cross-browser or assistive-technology audit.

**Maintainability and syntax:**

```sh
node --check jagent/static/workspace.js
```

Output: none; exit 0.

```sh
git diff --check
```

Output: none; exit 0.

**Feature branch:**

```sh
git branch --show-current
```

Output: `feat/atlas-terminal-ui`. No push or deployment performed.

## Run locally

With the project's existing `.env` and database configured:

```sh
uv run jagent serve
```

Open <http://127.0.0.1:8000>. No frontend build step or additional service is required. In this restricted workspace, uv's default cache is read-only; use `UV_CACHE_DIR=/tmp/jagent-uv-cache uv run jagent serve` or `.venv/bin/jagent serve` if necessary.

To reproduce tests elsewhere, configure `TEST_DATABASE_URL` for an isolated database ending in `_test` on the project's permitted PostgreSQL port, then run `JAGENT_TEST_POSTGRES=1 uv run pytest -q`. The browser check is optional: set `JAGENT_BROWSER_PYTHON` to an existing Python environment with Playwright and Chromium. Playwright has not been added to project dependencies.

## Deliberate limits

Structured skill strengths and “not demonstrated” claims are not connected to persisted briefings in the application. The interface displays stored assessments and source/profile evidence without splitting prose into invented claims. Assessments may contain older wording; the UI explains that missing profile evidence does not establish missing competence. Scores are explicitly text similarity, never hiring probabilities.

Career exploration and orchestration have no new navigation or simulated functionality. Applied records preserve existing behavior and do not introduce new editing or follow-up tracking. Review fragments still render the current queue server-side; pagination or lazy-loaded briefs would require a separate scalability task.
