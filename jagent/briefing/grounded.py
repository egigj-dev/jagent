# Grounded fit adapter; spans bind original inputs and controlled templates never reuse model prose.
import hashlib
import re

from jagent.briefing.contract import Briefing, Claim, ClaimDraft, InputPacket, SourceSpan
from jagent.briefing.evidence import SYNONYMS, mentions, normalize

FALLBACK = "Fit could not be established from verified evidence; review the posting and profile."
NEGATION = re.compile(r"\b(?:no|not|never|without|lack\w*|missing|limited|learning|beginner|wish|want|aspir\w*)\b", re.I)


def version(text: str) -> str:
    # Exact hashes, unlike the legacy normalized hashes, invalidate offsets after any edit.
    return hashlib.sha256(text.encode()).hexdigest()


def spans(text: str, source: str) -> list[SourceSpan]:
    result = []
    # Full sentences/lines prevent dropping a negation or a duration from a citation.
    for match in re.finditer(r"[^\n]+", text):
        for sentence in re.finditer(r"\S.*?(?:[.!?](?=\s|$)|$)", match.group()):
            start = match.start() + sentence.start()
            end = match.start() + sentence.end()
            quote = text[start:end]
            if 0 < len(quote) <= 600:
                result.append(SourceSpan(source=source, version=version(text),
                                         start=start, end=end, quote=quote))
    return result


def resolve(span: SourceSpan | None, source: str, text: str) -> bool:
    if span is None or span.source != source or span.version != version(text):
        return False
    if not 0 <= span.start < span.end <= len(text) or text[span.start:span.end] != span.quote:
        return False
    # Offsets explicitly disambiguate repeats; arbitrary substring citations are forbidden.
    return any(item == span for item in spans(text, source))


def skill_list(text: str) -> set[str]:
    # The entire value must be a list of known skills, never instructions, years or prose.
    parts = re.split(r"\s*(?:,|/|\band\b|&)\s*", text, flags=re.I)
    skills = set()
    for part in parts:
        canonical = next((key for key, aliases in SYNONYMS.items()
                          if part.casefold() in {key.casefold(), *aliases}), None)
        if canonical is None:
            return set()
        skills.add(canonical)
    return skills


def declared_skills(quote: str, source: str) -> set[str]:
    text = normalize(quote).removeprefix('- ').removeprefix('* ').removesuffix('.')
    if source == 'job':
        patterns = (r"(?:Required|Required skills|Requirements):\s*(.+)",
                    r"(.+?)\s+(?:is |are )?required")
    else:
        patterns = (r"(?:Skills|Technical skills):\s*(.+)", r"(.+?) experience")
    for pattern in patterns:
        match = re.fullmatch(pattern, text, flags=re.I)
        if match:
            return skill_list(match[1])
    return set()


def validate(draft: ClaimDraft, job: str, profile: str,
             job_span: SourceSpan | None, profile_span: SourceSpan | None) -> Claim:
    verdict, reason = 'insufficient_evidence', 'Missing, stale, mismatched or wrong-source citation.'
    job_ok = resolve(job_span, 'job', job) and draft.job_excerpt_id == job_span.excerpt_id
    profile_ok = (resolve(profile_span, 'profile', profile)
                  and draft.profile_excerpt_id == profile_span.excerpt_id)
    if draft.skill not in SYNONYMS:
        reason = 'Skill is outside the controlled vocabulary; no duration or arbitrary assertions allowed.'
    elif job_ok and mentions(job_span.quote, draft.skill):
        requirement = draft.skill in declared_skills(job_span.quote, 'job')
        if draft.kind == 'not_demonstrated':
            if draft.profile_excerpt_id is not None or profile_span is not None:
                reason = 'Evidence-gap claims must not carry a profile assertion.'
            elif not requirement:
                reason = 'A mention is not a verified advertised requirement.'
            elif mentions(profile, draft.skill):
                verdict, reason = 'contradicted', 'Profile mentions this skill; an absence claim is unsafe.'
            else:
                verdict, reason = 'supported', 'Verified requirement; skill not mentioned in supplied profile.'
        elif profile_ok and mentions(profile_span.quote, draft.skill):
            if NEGATION.search(profile_span.quote) or NEGATION.search(job_span.quote):
                reason = 'Negation or qualification requires manual review.'
            elif draft.kind == 'shared_mention':
                verdict, reason = 'supported', 'Only shared textual mentions are established; no proficiency claim.'
            elif requirement and draft.skill in declared_skills(profile_span.quote, 'profile'):
                verdict, reason = 'supported', 'Explicit posting requirement and profile skill declaration.'
            else:
                reason = 'Mentions alone cannot establish a strength or proficiency.'
    return Claim(**draft.model_dump(), status='passed_checks' if verdict == 'supported' else 'flagged',
                 verdict=verdict, reason=reason, job_span=job_span, profile_span=profile_span)


def build(posting_id: int, job: str, profile: str, model: str = 'deterministic-fit-v1') -> Briefing:
    jobs, profiles = spans(job, 'job'), spans(profile, 'profile')
    claims = []
    for skill in SYNONYMS:
        job_candidates = [span for span in jobs if mentions(span.quote, skill)]
        profile_candidates = [span for span in profiles if mentions(span.quote, skill)]
        required = next((span for span in job_candidates if skill in declared_skills(span.quote, 'job')), None)
        declared = next((span for span in profile_candidates if skill in declared_skills(span.quote, 'profile')), None)
        job_span = required or next((span for span in job_candidates if not NEGATION.search(span.quote)), None)
        profile_span = declared or next((span for span in profile_candidates if not NEGATION.search(span.quote)), None)
        if job_span is None:
            continue
        if profile_span is not None:
            kind = 'strength' if required and declared else 'shared_mention'
        elif required and not mentions(profile, skill):
            kind = 'not_demonstrated'
        else:
            continue
        draft = ClaimDraft(kind=kind, skill=skill, job_excerpt_id=job_span.excerpt_id,
                           profile_excerpt_id=profile_span.excerpt_id if profile_span else None)
        claims.append(validate(draft, job, profile, job_span, profile_span))
    return Briefing(packet=InputPacket(posting_id=posting_id, job_snapshot_id=version(job),
                                      profile_version=version(profile), model=model), claims=claims)


def render(briefing: Briefing, job: str, profile: str) -> str:
    # Revalidate at the presentation boundary: neither status nor model-supplied labels are proof.
    if (briefing.packet.job_snapshot_id != version(job)
            or briefing.packet.profile_version != version(profile)):
        return FALLBACK
    groups = {'strength': [], 'shared_mention': [], 'not_demonstrated': []}
    for claim in briefing.claims:
        checked = validate(ClaimDraft(**{key: getattr(claim, key) for key in ClaimDraft.model_fields}),
                           job, profile, claim.job_span, claim.profile_span)
        if checked.verdict == 'supported' and checked.skill not in groups[checked.kind]:
            groups[checked.kind].append(checked.skill)
    sentences = []
    if groups['strength']:
        sentences.append('Profile lists skills requested by the posting: ' + ', '.join(groups['strength']) + '.')
    if groups['shared_mention']:
        sentences.append('Posting and profile both mention ' + ', '.join(groups['shared_mention'])
                         + '; proficiency and requirement coverage are unverified.')
    if groups['not_demonstrated']:
        sentences.append('Advertised requirements not demonstrated in the supplied profile: '
                         + ', '.join(groups['not_demonstrated']) + '; this does not establish inability.')
    return ' '.join(sentences) or FALLBACK
