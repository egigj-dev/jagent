<!-- Final handoff; statuses apply to isolated previews and manual review gates keep production behavior unchanged. -->
# Night 2 handoff

B1 **WORKING offline preview / PARTIAL for production**: versioned Assessment
connects existing skill claims to anchored experience-duration/screening/logistics
observations, uncertain coverage, controlled explanations and heuristic transfer.
Long sentences retain bounded exact windows. In-memory serialized caching rejects
source/engine/schema changes and tampering. Analysis packets name the fit engine;
upstream fact model identity is separate. Failed grounded refreshes replace legacy
prose with the safe fallback. Durable database storage remains a SQL proposal.

B2 **WORKING offline preview**: current filters, freshness, queue and review gates
remain authoritative; validated B1 features feed stable heuristic ranking and
conservative read-only duplicate groups. Existing production scoring is unchanged.

C **WORKING offline preview**: validated selected/deduplicated B2 rows feed sample
observations, source-linked profile gaps/strengths, unknown constraints and at most
four bounded learning/documentation priorities. No market-wide inference is made.

D **WORKING decision / no framework implemented**: plain composition already provides
stage separation. No scheduler, new dependency or autonomous workflow is necessary.

## Delivery and defaults

Run `.venv/bin/python -m evals.intelligence_demo` for the connected 23-frozen-case +
two-synthetic-control preview. `--json` adds inspectable comparison/evidence IDs.
A separate synthetic test proves duplicate suppression and role/city separation.
All new recommendation/mentor behavior requires this explicit preview entry point.
Grounded Analysis keeps its existing default-off flag. No default dashboard/API
fields, database schema, source collector or matching weights were changed.

New source: `jagent/briefing/assessment.py`, `jagent/recommendations.py`,
`jagent/mentor.py`, `evals/intelligence_demo.py`.
New tests: `tests/test_intelligence.py`.
Changed source: `jagent/briefing/grounded.py`, `jagent/analysis.py`,
`evals/compare.py`, `evals/grounded.py`.
New documentation: ARCHITECTURE, B1_IMPLEMENTATION, B2_IMPLEMENTATION,
C_IMPLEMENTATION, DEMO, TESTS, REVIEW_CHECKLIST, HUMAN_REVIEW, D_DECISION and this
HANDOFF, all under `docs/night2/`.

Started from clean committed tree `83e0185` on `feat/b1-grounded-intelligence`,
except the existing untracked OVERNIGHT_CODEX.log and OVERNIGHT_RESULT.md. Those
files were never read or modified. All work remains unstaged for manual review.
No PR, commit, push, deployment, migration, live DB/model/network call, service or
production inspection occurred. Frozen recordings and original labels are unchanged.

## Tradeoffs and known limits

- Source resolution and deterministic revalidation do not prove semantic truth.
  Long sentences with negation conservatively abstain. Only a bounded English
  vocabulary and a few explicit constraint forms are recognized. Unknown skills,
  general model-driven complex extraction and multilingual parsing remain open.
- Years are observed in postings; candidate years, credentials, legal/screening
  eligibility and seniority mismatch are unknown. No candidate facts are invented.
- Transfer observations are narrow heuristics. Ranking receives no transfer points
  and no penalties for unknown eligibility or mere example/title gaps.
- Same company/title/location can hide distinct requisitions; exact location/title
  safeguards also miss some real duplicates. No destructive merge is performed.
- Saved items remain eligible but preview does not reproduce saved-last UI ordering.
- Grounded online mode refreshes explanations for all queued postings, but only
  requests facts that are missing or from another model (fixed 2026-11-06). In-memory storage is optional and not transactional with DB writes; durable
  provenance and atomicity need implementation before a production rollout.
- Non-fit facts retain legacy schema/verbatim checks; their semantic correctness is
  not certified. No optional dashboard integration was added.
- Reports are sample observations and heuristic movement, not measured relevance
  gains. Existing 118 pending legacy labels and all new semantic reviews remain
  pending. The versioned independent review template leaves verdicts blank.

Final offline suite: **454 passed, 94 skipped, one existing warning**.
Privacy audit and diff/fixture checks exit 0. See TESTS for exact commands and
observed outputs. All source behavior remains experimental and requires review.

## Next manual steps

Read REVIEW_CHECKLIST and HUMAN_REVIEW, inspect the complete diff including new
files, and run the exact commands in TESTS. Review real frozen sentences and all
constraint/gap interpretations before changing weights. Decide source retention,
private-cache access and an additive SQL adapter before enabling durable storage.
Keep feature flags off until reviewed. Verify production's scheduled run separately
under the owner's normal process; this session makes no production-state claim.
Commit selected files manually when satisfied, excluding the two overnight files.
