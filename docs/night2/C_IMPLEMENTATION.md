<!-- Mentor aggregation; rows share B1 evidence, counts are unique selected postings, and priorities are bounded. -->
# Sample Career Mentor

`mentor.summarize(rows, profile)` consumes B2 rows, verifies B1 assessments again
against the profile and job snapshots, and aggregates only eligible ranked group
representatives. This prevents exclusions or cross-source copies inflating sample
counts. Requests, strengths and profile evidence gaps retain posting IDs and exact
source excerpt IDs; full quotes can be resolved in the assessment/frozen input.
The report separates extraction interpretation (`deterministic heuristic`) from
source resolution, and human-verified requirement count is explicitly unknown.

Contradictory requirements are counted as unknown rather than confirmed requests.
Counts are deduplicated per skill and posting, including weaker preferred/example/
title levels with their levels preserved. Constraints are unique posting sets;
candidate coverage remains unknown. Seniority mismatch is unknown because posting
durations do not establish candidate seniority. At most four learning/documentation
priorities are emitted, sorted by observed gap count then skill name. A small or
empty cohort can yield fewer than two priorities; none are fabricated to meet a
quota. Each priority cites the observations and says the profile may omit experience
and that examples/title mentions need not be mandatory.

Example connected behavior: the frozen 10343 assessment supplies .NET/Azure title
gaps and work authorization/language/location/duration observations. 51827 supplies
Terraform/Kubernetes example gaps plus screening/duration observations. Depending
on explicit filters, dedupe and time, only eligible cases contribute to counts.
Two separate synthetic demo controls show a supported Python fit and an uncertain
Kubernetes mention; these are invented controls, not user credentials.

All conclusions are observations in the supplied sample. Queue-selected anonymized
postings are not a representative market survey. No user identity, career history,
guaranteed outcome or market-wide prevalence is inferred. Public reports use
controlled wording and citation IDs rather than private profile excerpts or raw
untrusted posting instructions. No UI route or default landing-page change is added.
