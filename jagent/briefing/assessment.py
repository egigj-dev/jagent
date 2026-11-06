# Versioned fit assessments; constraints cite job spans and store holds serialized private evidence.
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from jagent.briefing.contract import Briefing, ClaimDraft, SourceSpan
from jagent.briefing.grounded import (
    ENGINE_VERSION, FALLBACK, PREFERRED, build, render, spans, supports_skill, validate, version,
)

ASSESSMENT_VERSION = 'assessment-v1'
MAX_SOURCE = 32000
CONSTRAINT_PATTERNS = {
    'years': re.compile(r'\b(\d{1,2})\s*\+?\s*years?\b[’\'\s]*(?:of\s+)?(?:working\s+|industry\s+|professional\s+)?experience', re.I),
    'screening': re.compile(r'\b(?:security screening|security clearance|Certificate of No Objection)\b', re.I),
    'work_authorization': re.compile(r'\b(?:legally qualified|right to work|work authori[sz]ation|visa sponsorship|eligible to work)\b', re.I),
    'location': re.compile(r'\b(?:must (?:live|reside|be based)|live and work|on[- ]site|onsite|relocat\w*)\b', re.I),
    'language': re.compile(r'\b(?:fluency in|fluent in|proficiency in)\s+(?:English|German|French|Dutch|Albanian|Italian)\b', re.I),
}


class Constraint(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['years', 'screening', 'work_authorization', 'location', 'language']
    job_span: SourceSpan
    minimum_years: int | None = Field(default=None, ge=0, le=99)
    requirement: Literal['preferred', 'unclear'] = 'unclear'
    support: Literal['uncertain'] = 'uncertain'
    rationale: str = 'Posting observation only; coverage in the supplied profile is unverified.'


class TransferObservation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_skill: str
    target_skill: str
    profile_span: SourceSpan
    job_span: SourceSpan
    interpretation: Literal['heuristic_not_requirement_coverage'] = 'heuristic_not_requirement_coverage'


class Assessment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: str = ASSESSMENT_VERSION
    engine_version: str = ENGINE_VERSION
    briefing: Briefing
    constraints: list[Constraint]
    transferable: list[TransferObservation] = Field(default_factory=list)
    extraction: Literal['deterministic_heuristic'] = 'deterministic_heuristic'
    # Records the upstream fact generator separately; it does not own fit provenance.
    fact_model: str | None = None


def assess(posting_id: int, job: str, profile: str, fact_model: str | None = None) -> Assessment:
    if len(job) > MAX_SOURCE or len(profile) > MAX_SOURCE:
        raise ValueError('Preview sources exceed the 32000 character bound; supply an explicit bounded snapshot.')
    constraints = []
    for span in spans(job, 'job'):
        for kind, pattern in CONSTRAINT_PATTERNS.items():
            match = pattern.search(span.quote)
            if match:
                # Negated, optional and alternative durations are not minimum claims.
                years = int(match[1]) if kind == 'years' and not (
                    re.search(r'\b(?:no|not|never|without|optional|at most|up to)\b', span.quote, re.I) or PREFERRED.search(span.quote)
                    or re.search(r'\bor\b|\d\s*[-–]\s*\d', span.quote[max(0, match.start() - 12):match.end() + 12], re.I)) else None
                constraints.append(Constraint(kind=kind, job_span=span, minimum_years=years,
                                              requirement='preferred' if PREFERRED.search(span.quote) else 'unclear'))
    briefing = build(posting_id, job, profile)
    languages = {'Python', 'Java', 'C#', 'C++', 'Go', 'JavaScript', 'TypeScript', '.NET'}
    transferable = []
    for gap in briefing.claims:
        if gap.kind != 'not_demonstrated' or gap.verdict != 'supported' or gap.skill not in languages:
            continue
        source = next((claim for claim in briefing.claims
                       if claim.verdict == 'supported' and claim.kind in ('strength', 'shared_mention')
                       and claim.skill in languages and claim.profile_span is not None
                       and supports_skill(claim.profile_span.quote, claim.skill)), None)
        if source:
            transferable.append(TransferObservation(source_skill=source.skill, target_skill=gap.skill,
                                                    profile_span=source.profile_span, job_span=gap.job_span))
    return Assessment(briefing=briefing, constraints=constraints, transferable=transferable[:3], fact_model=fact_model)


def current(value: Assessment, posting_id: int, job: str, profile: str) -> bool:
    # Reconstruct at the trust boundary. Serialized verdicts, rationales and counts are untrusted.
    try:
        expected = assess(posting_id, job, profile, value.fact_model)
        return value == expected
    except (ValueError, TypeError):
        return False


def explanation(value: Assessment, job: str, profile: str) -> str:
    if not current(value, value.briefing.packet.posting_id, job, profile):
        return FALLBACK
    result = render(value.briefing, job, profile)
    if value.transferable:
        sources = sorted({item.source_skill for item in value.transferable})
        targets = sorted({item.target_skill for item in value.transferable})
        result += (' Heuristic transfer opportunity: profile work with ' + ', '.join(sources)
                   + ' may help learning ' + ', '.join(targets)
                   + '; it does not establish coverage of those requirements.')
    durations = sorted({item.minimum_years for item in value.constraints if item.minimum_years is not None})
    if durations:
        result += ' Posting states experience durations of ' + ', '.join(str(years) for years in durations) + ' years; candidate duration is unverified.'
    labels = {'years': 'experience duration', 'screening': 'security screening',
              'work_authorization': 'work authorization', 'location': 'location or attendance',
              'language': 'language proficiency'}
    kinds = sorted({item.kind for item in value.constraints})
    if kinds:
        result += ' Posting constraints to verify: ' + ', '.join(labels[kind] for kind in kinds) + '. Coverage in the supplied profile is unknown.'
    return result


def cache_key(posting_id: int, job: str, profile: str) -> str:
    return ':'.join([ASSESSMENT_VERSION, ENGINE_VERSION, str(posting_id), version(job), version(profile)])


def put(store: dict[str, str], value: Assessment, job: str, profile: str) -> None:
    posting_id = value.briefing.packet.posting_id
    if not current(value, posting_id, job, profile):
        raise ValueError('Assessment does not match current sources and engine.')
    store[cache_key(posting_id, job, profile)] = value.model_dump_json()


def restore(store: dict[str, str], posting_id: int, job: str, profile: str) -> Assessment | None:
    raw = store.get(cache_key(posting_id, job, profile))
    if raw is None:
        return None
    try:
        value = Assessment.model_validate_json(raw)
    except (ValidationError, ValueError, TypeError):
        return None
    return value if current(value, posting_id, job, profile) else None


def checked_proposals(proposals: list[dict], job: str, profile: str):
    # Optional caller-supplied structured proposals; no client, tools or network call exists here.
    # Exact canonical anchors and the same semantic validator govern each individual draft.
    accepted = []
    for proposal in proposals[:100]:
        try:
            draft = ClaimDraft.model_validate(proposal['draft'])
            job_span = SourceSpan.model_validate(proposal['job_span'])
            profile_span = SourceSpan.model_validate(proposal['profile_span']) if proposal.get('profile_span') else None
            claim = validate(draft, job, profile, job_span, profile_span)
            if claim.verdict == 'supported':
                accepted.append(claim)
        except (ValidationError, KeyError, TypeError, ValueError):
            continue
    return accepted
