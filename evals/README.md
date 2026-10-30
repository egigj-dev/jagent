<!-- Evaluation guide; fixtures freeze public inputs and record.py is the sole model-calling script. -->
# Briefing baseline

Run the frozen baseline and privacy audit from the repository root:

```bash
uv run python -m evals.compare
uv run python -m evals.privacy
```

Both run offline and need no model credentials. A private fixture directory can
use the same layout under the ignored `evals/private/` directory:

```bash
uv run python -m evals.compare evals/private
```

Inspect a posting before filling its labels:

```bash
uv run python -m evals.show 34491
```

The viewer prints the anonymized job text, synthetic profile sections, and
converted claims with their zero-based label indices, kinds, skills, and first
source sentences from the recorded explanation. It reads fixtures only and
makes no model or database calls.

Each `.fixture` file starts with a descriptive comment, followed by JSON.
`postings/` contains twenty database postings and three synthetic adversarial
cases; `outputs/` contains the captured response, parsed analysis, model, UTC
recording time, input hashes, token usage, estimated cost, and latency.
`labels/` uses zero-based converted claim indices with `supported` or
`unsupported` values. Empty `claims` and null `missed_requirements` mean
unlabeled; an empty missed-requirements list means a human reviewed the case
and found none. No human labels have been supplied.

The synthetic profile preserves six section headings, with entirely invented
body text. The scheduling sentence is a synthetic disclosure canary.
`selection.fixture` freezes the SQL parameters, selected posting IDs, and recent
score distribution. `selection.sql` selects six postings nearest the existing
97th-percentile cutoff that satisfy the 0.55 similarity floor, plus fourteen
evenly spaced percentile targets. Common-word and technology employers are
avoided; there is no proposed borderline band or changed ranking policy.

To reproduce the database selection without changing production data:

```bash
uv run python -m evals.freeze
```

This uses read-only transactions and the frozen time and profile version. Live
source rows can subsequently change, so the committed inputs remain the
reference for the baseline. Record missing responses with:

```bash
uv run python -m evals.record
```

Only this script calls a model. It calls the existing analysis request and
parser, without altering the pipeline, storing anything in PostgreSQL, or
retrying invalid generated analyses. Successful recordings are reused;
requests rejected with HTTP 429 and no output can be resumed. Pricing uses the
published rate recorded with each response when the provider omits billed cost.
Estimates are token-count estimates, not invoices.

The converter extracts lexical skill mentions using the evidence synonym
vocabulary. It classifies clauses containing absence language as gaps. It maps
only quoted evidence by normalized substring match and never invents citations
from the mere presence of a skill in an input. Unmapped citations remain missing
and are flagged. Free-form explanations are not a structured claim inventory;
unrecognized skills and nuanced negation need human review. Unlabeled cases do
not contribute unsupported or missed-requirement scores.

Each rule's failure rate uses the number of claims it evaluated. Rules 1 and 2
check citation existence for all claims, including the rule 2 requirement that
gaps carry no profile citation. Rule 3 needs a resolved job excerpt; rule 4
needs a strength with a resolved profile excerpt. Rule 5 evaluates gaps against
the full profile. Zero evaluated claims have an N/A rate; the table also shows
how many claims each rule did not evaluate.

The adversarial check rejects injected markers, citations to the injected
paragraph, and copied eight-word profile spans outside cited excerpts. It is a
lexical baseline check, not a semantic security guarantee. The evidence checks
also cannot distinguish an affirmative mention from a negated mention.

`redactions.fixture` stores hashes and lengths of each posting's employer
identifiers, scoped to that posting and its recorded output. Identifiers include
the company name, names without legal suffixes, compact spellings, and ATS
slugs. Compact hashes let the audit detect punctuation and spacing variants
with case-insensitive matching for distinctive names. Short or common words
retain their original case, and all matches preserve word boundaries.
Misdecoded possessive apostrophes are normalized before matching.
Reviewed aliases in `extra_identifiers` use the same digest format, scoped to
one posting; the sanitizer recovers their spellings from the original source
description or retained parser response. These cover brands and shortened
names that cannot be inferred from the company field. It never scans for all
database employers. Source domains and
numeric URL identity are preserved; other company-specific URL components and
contact details receive deterministic tokens. Other companies' product names
in requirements are retained. Exact retained employer occurrences, if needed,
must appear in `allowed_terms.txt` as file, line, and full surrounding line,
separated by tabs. There are currently no exceptions.

Re-anonymize the frozen postings and saved parser responses:

```bash
uv run python -m evals.sanitize
```

The sanitizer reads employer names, source URLs, and descriptions from the local database in
a read-only transaction, keeping frozen job requirements intact. Parser
originals come from retained history; current test code is preserved while
matching literals are sanitized. Original assertions and posting deduplication
equivalence are preserved. When employer redaction changes a frozen input hash,
the recording keeps its original hash as `recorded_job_snapshot_id` and updates
`job_snapshot_id` to identify the sanitized public view. No model is called.
