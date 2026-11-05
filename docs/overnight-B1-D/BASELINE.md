<!-- Session baseline; commands describe offline checks and counts describe frozen fixtures. -->
# Baseline — 2026-11-04

Workspace `/home/egigj/jagent-b1`, sole listed worktree, branch
`feat/b1-grounded-intelligence`, HEAD `5f25a005db9971a674ea854a1806a3a846d419b8`.
Initial status: `?? OVERNIGHT_CODEX.log` (preserved, excluded from commits).
`python --version`: command not found; `.venv/bin/python --version`: Python 3.12.3;
`uv --version`: uv 0.13.5. Start time 03:09 Europe/Tirane, comfortably before 06:30.

Inspected: AGENTS.md, README.md, pyproject.toml, docs/architecture.md,
jagent/{analysis,matching,profile,db,dashboard}.py, jagent/briefing/{contract,evidence}.py,
jagent/templates/posting.html, evals/{README.md,data,compare,record}.py,
evals/fixtures/{profile.md,seeded.fixture,postings,outputs,labels}, tests/conftest.py,
tests/test_{analysis,evidence,evaluation,dashboard,daily}.py and test isolation guards.

Flow: profile sections and posting text -> embeddings -> best-section cosine similarity
-> recent-cohort percentile -> queue -> analysis.chat JSON -> schema and posting-quote
checks (two attempts) -> posting_analysis facts and matches.explanation -> dashboard.
Actual ranking additionally permits local posting IDs in the queue; this is broader than
the architecture diagram's simple 0.55/97 thresholds. No ranking changes planned.
InputPacket, ClaimDraft, Claim, Briefing already exist but the production explanation
does not use them. Five lexical checks cannot establish semantic support or negation.
Smallest seam: opt-in application-owned explanation adapter before persistence, keeping
Analysis's serialized shape and the default path unchanged. No migration.

## Before-edit tests

`env -u JAGENT_TEST_POSTGRES -u TEST_DATABASE_URL -u JAGENT_BROWSER_PYTHON .venv/bin/python -m pytest -q tests/test_evidence.py tests/test_analysis.py tests/test_evaluation.py`

`71 passed, 16 skipped in 2.54s`

`env -u JAGENT_TEST_POSTGRES -u TEST_DATABASE_URL -u JAGENT_BROWSER_PYTHON .venv/bin/python -m pytest -q`

`334 passed, 94 skipped, 1 warning in 13.34s`

No failures. Warning: Starlette's httpx TestClient deprecation. DB tests are explicitly
opt-in and conftest replaces db.connect before collection; no test DB provisioned.
Browser test also needs opt-in DB and browser interpreter. Daily shell tests use a fake
uv executable in pytest temporary directories, never the actual daily pipeline.

`.venv/bin/python -m evals.compare` (exit 0): 23 valid historical recordings, 127
converted claims, all 127 flagged/unmapped, nine stored human labels (all supported,
case 1357), 118 unlabeled; no reviewed missed-requirement lists. Adversarial cases
900001 PASS, 900002 FAIL (QuuxDB contamination), 900003 PASS. Five seeded faults
caught, zero of three valid controls flagged. Historical estimated mean cost
$0.00203907 and mean latency 19.683s; no new inference performed.

The README's statement that no labels exist is stale. Preserve all labels; reviewer
identity/provenance is not recorded, so do not independently attest their quality.
Twenty anonymized selected postings + three synthetic attacks have recordings;
no complete twenty-case human correctness benchmark exists. QuuxDB regression is
already documented by test_evaluation; baseline parser accepts the contaminated text.

## Exclusions

No production or older-checkout edits/credentials/services, no DB connections,
network/model calls, scraping, dependencies, ranking changes, deployment or pushes.
Existing model fact fields remain outside the new fit-only adapter's guarantees.
B2/C require stronger labels; D needs measured justification. No agent delegation.
