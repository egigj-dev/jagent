<!-- B2 behavior; candidates carry B1 assessments and existing queue/filter gates control eligibility. -->
# Offline recommendation preview

`recommendations.preview(candidates, profile, filters, now)` consumes triples of
posting metadata, exact job snapshot and B1 Assessment. It recomputes assessment
validity and reuses `filters.passes_filters`, including existing activity,
location and title rules. Explicit `queued=True` is required. Only review actions
`None` and `later` can enter recommendations; `apply`, `skip` and unknown states
are excluded. Missing dates and malformed/naive timestamps fail closed. Missing
similarity is a documented zero base, not a fabricated embedding score.

Heuristic score: clipped prior similarity × 100, plus 4 per demonstrated required
skill, 2 per required skill declaration, 1 per preferred strength, and minus 4 per
required absence or explicit limitation. Example/title/unclear mentions and
unverified constraints receive no score adjustment. Missing profile evidence is
not inability. Constraints are surfaced for review; no legal/screening conclusion
is inferred from them. Stable ties use posting ID. Public rows retain prior rank,
prior score, preview rank/score, eligibility, reasons, group and source citation
IDs. Prior rank covers the supplied cohort; preview ranks only eligible unique
recommendations, so movement includes eligibility selection as well as weights.

Duplicate grouping reuses collection's `runner.make_dedupe_key`, with an additional
exact title check preserving programming punctuation and exact normalized location
sets. Missing company/title/location cannot merge. The eligible highest-scoring
member represents each group; an excluded member cannot suppress it. Grouping is
read-only and does not alter collector or database merges. URLs are not fetched
or used as identity proof. Identical company/title/city can still represent
separate requisitions; manually review these groups. Conservative city/title
matching also misses some true duplicates. Saved (`later`) items remain eligible;
this preview does not replicate the dashboard's saved-last display ordering.

Default collection, embedding, queue thresholds, reviews, matching SQL and dashboard
are unchanged. This is a pure explicit preview, not a new production ranker.
The demo uses synthetic broad filters and a fixed clock, not the user's preferences.
No human relevance labels exist for these weights. Movement and contract checks
are reported; there are no NDCG, recall or relevance-improvement claims.
