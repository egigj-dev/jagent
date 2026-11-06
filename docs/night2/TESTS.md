<!-- Validation record; commands are offline and counts distinguish current checks from earlier regressions. -->
# Validation

No Done when checklist was separately supplied; the requested completion checks
are mapped here to exact executed commands and observed output summaries.

Baseline full offline suite:

```sh
env -u JAGENT_TEST_POSTGRES -u TEST_DATABASE_URL -u JAGENT_BROWSER_PYTHON .venv/bin/python -m pytest -q
```

Observed baseline: `410 passed, 94 skipped, 1 warning in 15.71s`.
Final observed result with all new source/tests: `454 passed, 94 skipped, 1 warning in 24.59s`.
The existing warning is the Starlette/httpx TestClient deprecation. No tests were
disabled. Database and browser integration remain intentionally skipped; no real
model/API, scraping, embedding download or production service test was run.
These wall-clock observations are single runs, not a performance benchmark.

Targeted integration, safe fallback, provenance/cache and compatibility:

```sh
env -u JAGENT_TEST_POSTGRES -u TEST_DATABASE_URL -u JAGENT_BROWSER_PYTHON .venv/bin/python -m pytest -q tests/test_intelligence.py tests/test_grounded.py tests/test_grounded_repairs.py tests/test_evaluation.py tests/test_analysis.py
```

Observed checkpoint before the final transfer, failed-refresh and contradictory-mentor tests: `157 passed, 16 skipped in 10.39s`.
The final full suite above includes those additional passing tests (44 new cases
relative to baseline). Tests cover altered/stale/source-swapped/repeated anchors,
long text, profile omissions/limits, frozen postings, constraints, cache corruption,
packet engine identity, failed-refresh fallback, Analysis persistence via fake connection and explicit
in-memory store, eligibility/review/freshness exclusions, missing metadata, stable
ties, duplicate city/role separation, mentor aggregation, contradiction abstention and revalidation, no-data,
sanitation and the deterministic end-to-end demo. All DB access in new tests is
stubbed; optional structured proposals use fake data only.

Integrated demonstration:

```sh
.venv/bin/python -m evals.intelligence_demo
```

Exit 0. Output begins `Offline B1 → B2 → C | deterministic-fit-v3 | 23 frozen + 2 synthetic controls`.
It reports 25 ranking rows and an eligible/deduplicated sample of 9, with four
bounded priorities. See DEMO.md for representative observed rows and limitations.

Historical offline replay:

```sh
.venv/bin/python -m evals.grounded
```

Exit 0. Observed: `cases | 23`, `adapted_claims | 40`, `adapted_with_citations | 40`,
`adapted_gap_claims | 11`, `adapted_flagged | 0`, `adapted_abstentions | 5`,
`adversarial_after_pass | 3`, `Synthetic canned faulty narratives removed | 8/8`.
These counts concern the skill Briefing, not extra constraint observations.
Reclassification/source resolution is not human-supported precision. New claims
are unlabeled; the remaining 118 old converted claims are still unlabeled.

Legacy measurement/reporting semantics:

```sh
.venv/bin/python -m evals.compare
```

Exit 0. Observed: `Recordings | 23; missing 0`, `Claims total | 127`,
`Human labels | 9 labeled claims; 118 unlabeled`, `Seeded faults | 5 / 5`,
`Valid controls wrongly flagged | 0 / 3`.
Backward-compatible `Adversarial 900002 | FAIL` is retained, now accompanied by
`Adversarial 900002 marker appearance | True; instruction compliance | unreviewed`.
No new compromise or model-performance conclusion is inferred from that marker.

JSON preview (explicit temporary file, no repository artifact):

```sh
.venv/bin/python -m evals.intelligence_demo --json > /tmp/jagent-night2-preview.json
```

Exit 0, no stdout. Parsed verification of the JSON reported:
`25 ranking rows; 9 selected; 4 priorities; private-note and injection-marker checks passed`.

Privacy and whitespace checks:

```sh
.venv/bin/python -m evals.privacy
git diff --check
git diff --exit-code -- evals/fixtures
```

All three exit 0 with no output. Final repository checks also verify frozen fixtures
have no tracked changes. Overnight log/result files were not read or modified.

During development two existing frozen-case regressions failed under an overly
broad long-line negation guard; sentence scope fixed them. A new duration check
caught `Machine Learning` being treated as a duration negation; duration-specific
negation rules fixed it. These failures were not suppressed or re-labeled.
