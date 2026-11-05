<!-- Passing slice checkpoints; commands and counts track validation before the next slice. -->
# Checkpoints

1. Baseline inspected and recorded before code edits (BASELINE.md).
2. Evidence adapter + source-span validation + final-output regressions:
   `env -u JAGENT_TEST_POSTGRES -u TEST_DATABASE_URL -u JAGENT_BROWSER_PYTHON .venv/bin/python -m pytest -q tests/test_grounded.py tests/test_evidence.py tests/test_analysis.py tests/test_evaluation.py`
   -> `103 passed, 16 skipped in 1.86s`. Initial new stub test failed because Mock
   lacked a cursor context manager; corrected the stub, no application bypass.
   `git diff --check` -> empty output (exit 0).
   Next slice: offline paired comparison and annotation documentation; no B2/C work.
3. Paired evaluation and annotation inventory added. Targeted command above ->
   `108 passed, 16 skipped in 2.66s`. Includes explicit/env opt-in and default-off.
   Eight synthetic canned faults replaced; historical attack check improves 2/3 to
   3/3, with 25 cited claims and nine abstentions on 23 identical inputs.
4. First broader run after adding fixtures: `1 failed, 368 passed, 94 skipped,
   1 warning in 13.21s`. Existing privacy audit rejected a synthetic URL's path
   (`/leak`) as non-placeholder. Replaced it with the audit's accepted synthetic
   `https://example.com/jobs` in the new test/fixture; did not weaken the audit.
   Standalone `.venv/bin/python -m evals.privacy` then returned exit 0, no output.

Local commit attempt failed: `git add ...` and `git commit -m 'Add opt-in source-bound
deterministic fit explanations'` both report `fatal: Unable to create
'/home/egigj/jagent-b1/.git/index.lock': Read-only file system`. No commit created;
no permission escalation or alternative checkout attempted.
