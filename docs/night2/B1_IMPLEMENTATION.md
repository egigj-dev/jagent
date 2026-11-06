<!-- B1 implementation; Assessment wraps Briefing, engine hashes invalidate caches, and constraints remain uncertain. -->
# Grounded assessment preview

`jagent.briefing.assessment.assess(id, job, profile, fact_model=None)` connects the
existing Briefing/Claim/SourceSpan contracts to a serializable Assessment. Sources
are exact bounded text (at most 32,000 characters each); oversize direct inputs
raise a clear error. The Analysis adapter falls back safely for oversized inputs.
The usual analysis job snapshot remains title plus HTML-stripped description,
with its existing 8,000-character description cap. Hashes refer to that snapshot,
not to original HTML. Profile prose is never included in public reports.

Existing repaired required/preferred/example/title/contradiction/polarity rules
are retained. Long sentences now produce canonical 600-character windows with
120-character overlap and exact offsets, rather than disappearing. Full original
sentence negation causes conservative abstention outside a window's local context.
This intentionally loses some positive evidence; it does not claim complete
semantic understanding. A preliminary whole-line guard broke 51827 and 52454;
it was corrected to sentence scope and existing regressions were preserved.

Assessment adds anchored observations for numeric experience duration, screening,
work authorization, attendance/location and a few explicit language phrases.
Durations with detected negation, preference, ranges or local alternatives do not
become minimums. Candidate duration, clearance, legal eligibility and language
proficiency remain unknown even if the profile mentions related words. Constraints
are heuristic observations, not verified eligibility decisions. Multiple spans
may describe the same constraint; mentor counts unique posting IDs.

A small language-to-language transfer observation may link work evidence to a
language gap. Both source spans are retained. The controlled renderer calls this
a heuristic learning opportunity and explicitly says it does not establish
requirement coverage. No ranking points are awarded for this inference.

`checked_proposals` accepts explicit caller-supplied structured fake/model drafts,
checks canonical job/profile citations and the existing semantic validator, and
selectively rejects invalid drafts. It has no model client, network access or
automatic invocation. Unknown skills remain outside the controlled vocabulary.
Model-powered complex extraction and general multilingual parsing are unfinished.

## Persistence and compatibility

`Assessment` contains schema version `assessment-v1`, fit engine
`deterministic-fit-v3`, exact job/profile hashes in its packet, source spans,
constraints, and heuristic transfer observations. The packet's `model` now names
the deterministic fit engine on the actual Analysis path. The upstream fact
model is separately recorded as `fact_model`; it does not certify fit semantics.

`put(dict, assessment, job, profile)` serializes private evidence, and
`restore(dict, posting_id, job, profile)` reconstructs and compares the full current
assessment before returning it. Key identity includes schema, engine, posting,
job and profile. Source edits, source swaps, stale engines, wrong IDs, altered
excerpts, invented constraints or changed labels fail closed. Legacy prose and
profile copies cannot be restored as assessments. This deliberately simple
in-memory adapter is usable by the demo and explicit `analyze(assessment_store=...)`
callers; it is not durable production storage. Public reports expose citation IDs,
not raw profile quotes. The caller must protect serialized private evidence.

Grounded mode remains off by default (`JAGENT_GROUNDED_EXPLANATIONS=1` or explicit
`grounded=True`). It now bypasses legacy profile explanation copying and refreshes
all queued analyses instead of trusting same-model cached prose. This can repeat
upstream fact calls in a future online run; no such calls were made here. A failed grounded refresh writes the safe fallback instead of leaving old prose
visible as a current result. Default-off behavior retains legacy caching. Database fact model identity and existing
Analysis serialized keys are preserved. `_briefing` and `_assessment` are private
attributes. Only fit explanations receive these checks: salary, seniority,
employment and fact language values keep the existing verbatim/schema validation.

## Additive SQL proposal for later review — never executed

The schema is unchanged. A possible explicit, reviewed addition to `schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS fit_assessments (
    posting_id bigint NOT NULL REFERENCES postings(id),
    profile_id bigint NOT NULL REFERENCES profile(id),
    schema_version text NOT NULL,
    engine_version text NOT NULL,
    job_sha256 text NOT NULL,
    profile_sha256 text NOT NULL,
    assessment jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (posting_id, profile_id, schema_version, engine_version,
                 job_sha256, profile_sha256)
);
```

Review actual FK types, retention of exact source snapshots, privacy controls and
atomicity with explanation updates before implementing a SQL adapter. Revalidate
stored JSON against current sources at read time; never rely on an explanation's
presence or upstream model name. No migration, backfill or startup DDL is added.
