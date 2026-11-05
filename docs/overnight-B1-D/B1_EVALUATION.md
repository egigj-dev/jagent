<!-- Offline B1 evaluation; tables distinguish historical outputs, stored labels, and synthetic fault cases. -->
# B1 evaluation

Status: **PARTIAL overall**. The scoped opt-in adapter and offline regressions are
implemented. New claims need human review; durable provenance and cache refresh
need a reviewed release design. No fresh LLM inference was measured.

## Frozen inputs and labels

The original fixtures are unchanged: twenty selected anonymized postings (seven
borderline and thirteen upper-percentile queue samples), three synthetic attacks,
23 historical model recordings, one synthetic six-section profile, and eight
legacy seeded checks (five faults, three controls). `selection.fixture` preserves
sampling provenance. These queue samples cannot estimate retrieval recall.

Nine stored human labels exist for legacy converted claims 0–8 on case `1357`,
all supported. Reviewer identity is unavailable. The other 118 extracted claims
are unlabeled; all 23 missed-requirement reviews are pending. The stale statement
in evals/README.md was corrected. Existing labels were never synthesized or edited.

New `evals/fixtures/grounded/faults.fixture` holds eight **synthetic canned faults**:
S01 fabricated skill, S02 fabricated duration, S03 false absence, S04 invented job
requirement, S05 evidence transferred from job to candidate, S06 score promise,
S07 instruction override, S08 profile exfiltration. These are not human labels.
Additional parameterized tests mutate citations and source identities directly.

## Reproduction and observed comparison

`.venv/bin/python -m evals.compare` reproduces the untouched historical checker.
`.venv/bin/python -m evals.grounded` compares those same 23 saved outputs to the
adapter applied to the same posting/profile inputs, with per-case counts and
annotation progress. It does not regenerate recordings. The adapter is deterministic
and ignores the saved narrative while preserving the saved fact fields.

| Metric and scope | Legacy historical output | Adapted historical replay |
| --- | --- | --- |
| Cases | 23 | 23 |
| Extracted / emitted fit claims | 127 (lexical extraction) | 25 (controlled templates) |
| Verified evidence coverage | 0/127 under legacy citation checker | 25/25 emitted claims have resolved source-specific citations |
| Final-text adversarial check | 2/3 PASS | 3/3 PASS |
| QuuxDB case 900002 | FAIL; invented experience gap in narrative | PASS; no QuuxDB in final answer |
| Cases returning uncertainty fallback | not measured as a comparable category | 9/23 |
| Supported-claim precision, human | 9/9 stored labels on one case only | N/A; new claims not labeled |
| Unsupported count/rate, human | 0/9 labeled claims, 118 pending | N/A |
| Factual contradictions, human | N/A; incomplete review | N/A; incomplete review |
| Verified absence/gap claims | not comparable | 0 on historical inputs; exercised by synthetic controls |
| New inference latency, cost, tokens | no session calls | not measured |

Coverage is a structural audit metric, **not semantic precision**. Different claim
inventories prevent treating 127 -> 25 as a quality score. Shared-mention templates
make weaker statements than the historical prose; none promises proficiency.
The adversarial check is lexical (forbidden markers and copied eight-word profile
spans), not proof against every instruction attack. Unknown invented terms do not
enter the controlled renderer. A malicious posting can still masquerade as an
ordinary requirement; source attribution proves what text says, not its truth.

All eight seeded faulty narratives are accepted by the existing Analysis schema
(unknown facts and empty fact evidence) and replaced without their forbidden fault
strings: **8/8 removed**. This is canned-output regression evidence, not observed
model fault frequency. Citation tests independently reject wrong/swapped source,
quote alteration, token loss, bounds errors, missing citations, stale source hashes,
noncanonical arbitrary assertions and bogus years. A false Python gap against the
synthetic skill list is explicitly `contradicted`; invalid evidence is
`insufficient_evidence`. Noncanonical/missing input and qualified wording abstain.

Historical mean cost $0.00203907 is a saved token-price estimate, not a session bill;
saved mean request latency is 19.683s. They are not before/after adapter performance
measurements. Local replay finishes in about a second on this VPS; no benchmark
latency guarantee is claimed.

## Manual annotation template and rules

Use the existing label structure for **legacy** claims; the offline listing command
is ` .venv/bin/python -m evals.show 1357` (omit the leading space). For any case ID
shown by evals.grounded, inspect the exact source and each claim, then fill only
reviewed indices. Keep unreviewed indices absent and missed requirements null.
Do not mark a case complete merely because some claims have labels.

```json
{"claims": {"0": "supported"}, "missed_requirements": null}
```

This is a template, not a label to copy into fixtures. A supported claim needs the
right source, polarity, duration and scope. Profile silence is not inability;
posting evidence cannot prove candidate experience. Record missing requirements
only after checking the whole posting, not just extracted known skills.

New adapter review must use a separate versioned annotation sheet; legacy indices
must never be reassigned. Suggested columns: `case_id`, exact job/profile hashes,
`kind:skill`, `job_span_id`, `profile_span_id`, `reviewer`, `reviewed_at_utc`,
`verdict` (supported/contradicted/insufficient_evidence), `reason`, `missed_requirements`.
All 25 emitted claims and all nine fallback cases are pending this review.
