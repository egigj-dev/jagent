<!-- Integration record; source commits preserve both input trees and verification paths identify isolated tests and release artifacts. -->
# Atlas × Terminal + Milestone A integration

Candidate: `integration/atlas-milestone-a` in `/tmp/jagent-integration`.
Common input HEAD: `aaba840`. Both inputs contained uncommitted work, rather than
separate implementation commits. The isolated integration records them separately:

- `7ec5c33`: exact current UI snapshot, including its 17 dirty files.
- `03b0852`: reviewed Milestone A patch, matching all 31 dirty files in its input tree.
- A subsequent integration commit: release migration, regression coverage, one Saved
  count-label correction, and the deployment/rollback plan.

Neither `/home/egigj/jagent` nor `/tmp/jagent-milestone-a` was staged, committed,
reset or switched. Their branch, HEAD, Git status and dirty-file hashes remain
unchanged. The milestone-only patch is preserved in the review artifacts. All
Git commits made during integration are local to the new clone.

## Findings and changes

**Zero new postings is not a classifier bug.** Collection uses successful
`fetched > 0` results, independently of `new`. A new PostgreSQL regression inserts
two jobs, re-fetches them through the real persistence path, records `fetched=2`
and `new=0`, and verifies daily success/exit 0 with cached processing. No classifier
policy was changed. If every source returns zero fetched postings, the documented
minimum-coverage policy still fails the run; that is a separate case.

**Migration is additive and repeatable.** `deploy/milestone-a.sql` contains only
the canonical `pipeline_runs` CREATE TABLE inside a transaction, with a five-second
lock timeout. Tests apply it twice to an isolated schema containing the old app
schema and real profile/posting/match/review rows. Data remains unchanged, all
three outcomes plus unfinished runs can be stored, and an invalid outcome fails
its constraint. Normal rollback leaves this extra audit table in place. The
canonical DDL remains in `schema.sql`; a test prevents the release SQL diverging.
No migration tool or new dependency was introduced.

**One integration presentation regression was fixed.** Saved history now includes
inactive/unqueued records, so the inherited “in queue” total label was misleading
in that view. It now reads “saved”; default Opportunities still reads “in queue”.
A server regression pins the count text, and Chromium exercises an expired saved
role, its retained notes, warning, and subsequent Skip action. The approved visual
layout and source CSS were preserved.

**No other application regressions were found in covered behavior.** Tests cover
expiry/date boundaries, current counts, historical Saved/Applied, source error
preservation, degraded/failed outcomes, form saves, keyboard navigation, review
persistence, error recovery and disabled/blocked JavaScript. Browser artifacts
use an environment-selected output directory so the earlier milestone evidence
is not overwritten.

## Verification

A fresh virtual environment was built from the unchanged `uv.lock` using uv,
then checked for dependency compatibility. It is an independently installed
integration environment, not the earlier borrowed interpreter symlink. The
Playwright browser executable remains in its existing optional test environment.
No matching, filtering, embedding, profile or analysis algorithm/model module,
`pyproject.toml` or `uv.lock` changed.

The final combined test command, from the candidate checkout:

```bash
env JAGENT_BROWSER_PYTHON=/home/egigj/.cache/uv/archive-v0/n169s7cegO4KK6xL/bin/python JAGENT_BROWSER_ARTIFACTS=/tmp/jagent-integration-review/browser .venv/bin/python /tmp/jagent-integration-review/run-tests.py -q -s
```

Result: **428 passed, 1 warning in 44.01s**. New database work is restricted to
loopback port 5434 and a database ending `_test`; migration tests create and remove
a private test schema. Browser acceptance covers 320/390/768/1024/1440px and all
existing pages. Screenshots for the expired Saved role, Health and mobile selected
brief were visually inspected. The one warning is the existing Starlette/httpx
deprecation. uv also reports its existing build-backend version-range warning;
locked installation, CLI loading and all tests succeed without changing versions.

All three rendered systemd units pass `systemd-analyze verify`. The daily shell
passes `bash -n`, JavaScript passes `node --check`, and diffs pass whitespace checks.
SuccessExitStatus=2 and the daily entry-point exit propagation are covered by tests;
actual production unit execution has deliberately not been triggered.

## Limits and release handoff

The production-schema preflight was read-only and found `pipeline_runs` absent.
No production DDL/data writes, service restart, external job collection or paid AI
calls were performed. Dependency downloads installed existing locked packages only
inside the integration environment. Both live services still use the old mutable
checkout until rollout; the candidate moves them to a fixed release directory.

The Milestone A adversarial diagnosis remains unresolved: 900002 still FAILs the
lexical adversarial check and demonstrates narrative contamination; its output
was not regenerated or expectations weakened. Duapune's external collector and
the known source timeout are outside this integration; no repair is claimed.
Coverage from only one nonempty source meets the existing minimum but does not
promise comprehensive market coverage. Production scheduling/exit behavior and
backup restoration remain deployment-time observations, not unit-test guarantees.

Use [the exact deployment and rollback plan](deployment-milestone-a.md). Stop before
its production maintenance section until rollout is authorized. Never invoke
`init-db` just for this migration: it also performs a deduplication backfill.
A timer restart can immediately catch up a missed run because Persistent=true;
resume it only when ready for normal external collection and paid processing.

Full evidence, source-input fingerprints, release archives and a Git bundle are
under `/tmp/jagent-integration-review`. Move those artifacts to durable storage
before `/tmp` cleanup; the final clean commit is recorded in its release manifest.
