<!-- B1 design and constraints; flag controls the adapter and spans preserve original input identity. -->
# B1 implementation

The existing InputPacket/ClaimDraft/Claim/Briefing layer is reused. SourceSpan adds
strict source identity, exact SHA-256 version, zero-based Python character offsets
(start inclusive, end exclusive), and the original full sentence/line quote, capped
at 600 characters. Claim adds verdict, reason and optional job/profile spans;
legacy callers retain defaults. `shared_mention` is a new, deliberately weak kind.
Legacy lexical checks remain available, with required profile citations extended
to this kind; their known semantic limitations are unchanged.

`jagent.briefing.grounded` contains plain functions:

- `build(posting_id, job, profile, model)` constructs bounded vocabulary claims.
- `validate(draft, job, profile, job_span, profile_span)` independently resolves
  both sources, IDs, exact hashes, bounds, full sentence boundaries and content.
- `render(briefing, job, profile)` revalidates every claim and packet hash, ignoring
  application/model status labels including manual_override. It emits fixed prose.

Normalization is used only for lexical interpretation; span matching is exact,
so even harmless source edits invalidate offsets. Repeated identical sentences
have distinct offset IDs; there is no first-substring-match ambiguity. No dropped
negation, arbitrary joined quote or synthesized label becomes independent evidence.
Strict Pydantic bounds reject empty/oversized excerpts; the resolver checks again.

Strengths require an explicit recognized job requirement (`Required: Python`,
`Python is required`, or lists using existing aliases) and a profile declaration
(`Skills: Python` or `Python experience`). Years and achievements cannot be added.
Shared mentions use separate source spans and say only that both sources mention
a known skill, with proficiency/coverage explicitly unverified. Negative/qualified
sentences abstain. Gap claims require a recognized requirement and no mention of
that skill or an alias anywhere in the whole profile; they say not demonstrated
in the supplied profile and explicitly do not establish inability. A supplied
profile mention contradicts an absence claim. Optional skills, questions, unknown
skills, partial/malformed inputs and unsupported non-English requirements do not
silently become gaps. This is a small English grammar, not a general NLP parser.

## Adapter boundary and compatibility

`analysis.ground_analysis(candidate, job, profile, posting_id, model)` retains
Analysis's existing serialized fields and replaces only explanation. Provenance
is available as `result._briefing` in memory and through the pure build function.
The source job is title + sanitized/truncated description from job_input (HTML
removed, description capped at 8000 characters); hashes/offsets refer to that exact
representation, not the original HTML or DB description. Company/location labels
are excluded from fit evidence. Existing fact quote validation is unchanged.

`analyze(..., grounded=True)` or `JAGENT_GROUNDED_EXPLANATIONS=1` opts in before
persistence. Default off preserves existing behavior. Explicit False overrides the
environment. No schema, dependencies, ranking, dashboard or API field changes.
A stubbed connection test proves the persisted explanation is adapted with one
stub model call; explicit opt-in, environment opt-in and default-off are covered.

The prompt explicitly treats posting/company data as untrusted and forbids it
from changing profile, score, rules, destinations or output policy. Requests have
no tools/functions enabled; final text never copies arbitrary model prose, URLs,
private sentences or attacker-selected skill names. This protects this fit output
boundary, not every model fact field or all forms of provider data disclosure.
The existing request still sends the whole profile to the configured provider.

## Fallback and regression behavior

QuuxDB recording 900002 is passed through the actual Analysis parser, then the
adapter: the final answer omits QuuxDB and the rating instructions and retains
Python/SQL shared mentions. Recorded instruction and profile-leak attacks also
pass final-text checks. Synthetic score override, secret-copying, wrong-source,
negative-profile and ordinary positive/gap controls are independently tested.
When nothing validates, FALLBACK asks the reader to review posting/profile.
Useful validated claims survive independently; one invalid claim does not discard
all valid ones. No new retries or semantic critic: deterministic fallback needs
neither. The pre-existing two-attempt fact/schema/API loop remains unchanged.

## Release limitations

**This is experimental, not production-ready.** Provenance is transient: existing
DB columns retain the compact explanation and fact evidence, not structured fit
claims. The pure function allows reproduction only if exact inputs are retained.
A reviewed persistence design is required for durable auditability. Do not overload
existing evidence keys with JSON that the dashboard would display as posting quotes.

Existing same-model cached explanations are not regenerated by enabling the flag,
and profile-copy paths may retain old prose. No automated invalidation or backfill
was attempted. Fact fields (salary, seniority, languages, contract) still have only
the prior schema/verbatim-quote checks; semantic fact correctness is outside this
fit adapter. Human review is pending. Long evidence lines, indirect wording,
unknown skills and multilingual sources can lose useful matches; nine of 23
historical cases abstain. No semantic critic is justified by the available labels.
