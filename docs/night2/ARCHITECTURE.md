<!-- Architecture map; engine versions bind fit evidence and preview stages share Assessment. -->
# Night 2 architecture

Explicit offline entry point: `python -m evals.intelligence_demo`.

Exact bounded job/profile text → existing grounded Briefing (skill claims) →
Assessment (Briefing + anchored years/logistics constraints) → preview ranking
(existing filters + queue/review gates + conservative duplicate groups) → sample
mentor observations and bounded priorities. All stages are pure except an explicit
in-memory serialized cache. No database, model, browser or network is needed.

`jagent.briefing.grounded` owns source spans and semantic checks.
`jagent.briefing.assessment` owns versioned serialization, constraints, cache and
controlled explanations. `jagent.recommendations` reuses `filters.passes_filters`
and `runner.make_dedupe_key`. `jagent.mentor` consumes validated assessments from
ranking. A deterministic engine identity is distinct from the recorded model.

Default production matching, schema, dashboard and serialized Analysis keys stay
unchanged. Grounded explanations remain opt-in. In that mode legacy explanation
copying is bypassed and queued analyses are refreshed rather than trusting legacy
same-model text. Durable SQL storage is a review proposal, never auto-applied.

Constraints are heuristic posting observations; candidate years and legal/screening
eligibility remain unknown. Citation resolution proves source identity, not truth.
Ranking weights are reviewable heuristics, not measured relevance gains. Frozen
queue-selected fixtures do not describe the whole job market. No workflow framework
or autonomous agent is needed for this straight-line offline composition.
