<!-- Design decisions; each entry records the choice, alternative and reason. -->
# Design decisions

## A workflow with one LLM step

**Choice:** Deterministic collection and ranking, then one LLM analysis step.
**Alternative:** An agent system that browses and interprets every source.
**Why:** Reproducible collection is easier to test and maintain: “use the LLM to
write the parser, not to be the parser”.

## Postings as the seam

**Choice:** The postings table separates collecting from judging.
**Alternative:** Fetch, rank and explain inside each source adapter.
**Why:** Collection can retry independently; every source shares the same judging logic.

## Deduplication

**Choice:** Normalize company and title, merging other URLs and locations.
**Alternative:** Treat each source URL as a separate opportunity.
**Why:** Cross-posted roles should appear once without losing application links or locations.

## Section scoring

**Choice:** One embedding per profile section, with max-over-sections scoring.
**Alternative:** One embedding for the entire profile, or averaging section scores.
**Why:** A strong match to one area of experience should survive unrelated sections.

## Relative shortlist

**Choice:** Percentile >= 97 plus a similarity floor.
**Alternative:** A fixed similarity threshold alone.
**Why:** Relative ranking adapts to the candidate pool while the floor rejects weak matches.

## Evidence-backed extraction

**Choice:** Structured LLM extraction with verbatim evidence validation.
**Alternative:** Free-form explanations accepted without checking source text.
**Why:** Schema checks and source evidence make unsupported claims easier to reject.

## Facts and views

**Choice:** Store facts such as `expires_at`; compute views such as “days left”.
**Alternative:** Persist relative display values.
**Why:** Relative values become stale as time passes; timestamps remain useful in UTC.

## Meaningful health checks

**Choice:** Account for ATS and early-stopping exceptions; tolerate up to 10% retry
failures, but fail when every attempt fails.
**Alternative:** Require positive counts everywhere and fail on any retry.
**Why:** Empty ATS boards and stopping at known jobs can be normal; small transient
failures should retry without hiding a broad outage.

## Profile versions

**Choice:** Store every activation; filters-only changes reuse explanations.
**Alternative:** Overwrite the active profile and regenerate every explanation.
**Why:** Version history preserves context, while unchanged profile text avoids redundant analysis.

## Home-connection imports

**Choice:** Collect bot-protected sources from a home connection and import files.
**Alternative:** Fetch every source directly from the server.
**Why:** Some sites block data-center traffic; file imports keep that collection boundary explicit.
