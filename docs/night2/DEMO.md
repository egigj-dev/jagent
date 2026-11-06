<!-- Offline demo guide; fixed clock and explicit synthetic filters make the B1/B2/C report reproducible. -->
# Integrated offline preview

From this checkout, with no credentials, database or model required:

```sh
.venv/bin/python -m evals.intelligence_demo
.venv/bin/python -m evals.intelligence_demo --json
```

Both commands read only frozen repository fixtures and run all stages in process.
The JSON form adds reasons, evidence IDs, constraint observations and the paired
comparison. It does not print internal profile citations. Twenty-three frozen
cases and two invented controls use the same synthetic fixture profile. The
clock is 2026-10-30 UTC; filters are explicitly synthetic and do not load settings
or claim to reproduce the user's actual preferences.

Representative observed console rows (the full command includes all 25 cases):

```text
Offline B1 → B2 → C | deterministic-fit-v3 | 23 frozen + 2 synthetic controls
ID | eligible | prior rank/score | preview rank/score | duplicate group
51827 | True | 3/0.6652556678811985 | 1/66.5256 | 51827
910001 | True | 9/0.6 | 2/64.0 | 910001
10343 | True | 7/0.6095019092178298 | 4/60.9502 | 10343
910002 | True | 10/0.6 | 5/60.0 | 910002
900002 | False | 24/None | None/4.0 | None
C | Observations in the supplied sample; not a representative market survey. Sample size: 9.
Priority | Azure | 2 posting(s): 51827,10343 | The supplied profile may omit experience; examples and title mentions may not be mandatory.
```

B1 examples: 10343 reports .NET/Azure title gaps, 3-year posting duration and
unknown language/location/work-authorization coverage. 51827 reports qualified
Terraform/Kubernetes/Azure examples, 5-year posting duration and unknown security
screening coverage. 900002 retains supported Python and uncertain shared SQL
without the injected markers. Its missing queue/date metadata excludes it from
recommendations, while it still exercises B1 adversarial handling. Synthetic
910001 shows positive fit; 910002 intentionally falls back for an unclear
Kubernetes mention. Duplicate grouping and exclusion are exercised with separate
synthetic tests; this frozen demonstration happens to have no merged groups.

`--json` comparisons link the unchanged recorded narrative, apply the Night 1
controlled renderer to **current extracted claims**, and show the richer current
assessment explanation. The template field is not a byte-for-byte replay of the
old engine: source windows/extraction changed. Non-attack recorded narratives
are included for comparison; the attack narrative is referenced by file instead
of echoing its markers. No fresh model inference occurs. New counts, movements
and marker checks are structural observations, not human semantic quality scores.
