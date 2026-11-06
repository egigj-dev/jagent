# Grounded fit adapter; spans bind original inputs and controlled templates never reuse model prose.
# FIT_SKILLS is the fit vocabulary, a superset of the frozen evaluator's SYNONYMS. Levels are required,
# preferred, example (a named instance of a wider ask), title, not_required or unclear; ENGINE_VERSION invalidates stored assessments when these rules change.
import hashlib
import re

from jagent.briefing.contract import Briefing, Claim, ClaimDraft, InputPacket, SourceSpan
from jagent.briefing.evidence import SYNONYMS, mentions, normalize

ENGINE_VERSION = 'deterministic-fit-v4'
FALLBACK = "Fit could not be established from verified evidence; review the posting and profile."
# "learning" marks an aspiration ("learning Kubernetes"), but not when it names a field such as
# Machine Learning, which appears in most AI postings and would otherwise suppress requirements.
NEGATION = re.compile(r"\b(?:no|not|never|without|lack\w*|missing|limited"
                      r"|(?<!machine )(?<!deep )(?<!reinforcement )(?<!statistical )learning"
                      r"|beginner|wish|want|aspir\w*)\b", re.I)
# Added here, not in SYNONYMS, so that the frozen lexical evaluator keeps its historical counts.
FIT_SKILLS = {**SYNONYMS, '.NET': ('.net',)}
REACT_CONTEXT = re.compile(r"(?:skills?|stack|using|with|in|and|experience)\s*:?\s*$"
                           r"|(?:TypeScript|JavaScript|Node|Vue|Angular|HTML|CSS)\s*[,/]\s*$", re.I)
REACT_AFTER = re.compile(r"\s*(?:\.?js\b|native\b|developer|development|engineer|experience|components?\b|"
                         r"[,/]\s*(?:TypeScript|JavaScript|Node|Vue|Angular|HTML|CSS)|[.;]?\s*$)", re.I)
NOT_REQUIRED = re.compile(r"\b(?:not|no|never|isn't|aren't)\b[^.]*\b(?:required|needed|necessary|essential|mandatory)\b"
                          r"|\boptional\b", re.I)
PREFERRED = re.compile(r"\b(?:nice[- ]to[- ]have|preferred|prefer|bonus|a plus|desirable|ideally)\b", re.I)
# A bare "requirements" is excluded: "depending on project requirements" says nothing about a skill.
REQUIRED = re.compile(r"\b(?:required|requires?|must|mandatory|essential|we expect|expected to have|proficien\w+|"
                      r"expertise (?:in|with)|needs? (?:to have|experience|strong|solid)|"
                      r"(?:proven|hands-on|solid|strong|extensive|demonstrated) (?:\w+ )?(?:experience|knowledge|skills?)|"
                      r"\d+\+? years of)\b|\brequirements?\s*:", re.I)
EXAMPLE = re.compile(r"\be\.g\.|\bfor example\b|\bsuch as\b|\bor (?:similar|equivalent)\b", re.I)
WINDOW = 100
HEADING_REQUIRED = re.compile(r"\b(?:requirements?|required|qualifications?|must[- ]haves?|what you(?:'ll)? need|"
                              r"what we(?:'re| are)? looking for|you have)\b", re.I)
HEADING_PREFERRED = re.compile(r"\b(?:nice[- ]to[- ]haves?|preferred|bonus|desirable|plus)\b", re.I)
PRONOUN = re.compile(r"\b(?:it|this|that|them|those)\b", re.I)
WORK = re.compile(r"\b(?:built|build|deployed|developed|shipped|maintained|implemented|operated|ran)\b", re.I)
TOY = re.compile(r"\b(?:demo|tutorial|coursework|course|bootcamp|toy|practice)\b", re.I)
STRONG = ('required', 'title', 'preferred', 'example')


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
            # Long single-line sentences are retained as overlapping bounded windows.
            # Interpretation below abstains when a long sentence contains negation, since a
            # window alone cannot establish its scope. Offsets still bind exact text.
            offset = start
            while offset < end:
                stop = min(offset + 600, end)
                result.append(SourceSpan(source=source, version=version(text),
                                         start=offset, end=stop, quote=text[offset:stop]))
                if stop == end:
                    break
                offset = stop - 120
    return result


def resolve(span: SourceSpan | None, source: str, text: str) -> bool:
    if span is None or span.source != source or span.version != version(text):
        return False
    if not 0 <= span.start < span.end <= len(text) or text[span.start:span.end] != span.quote:
        return False
    # Offsets explicitly disambiguate repeats; arbitrary substring citations are forbidden.
    return any(item == span for item in spans(text, source))


def fit_mentions(text: str, skill: str) -> bool:
    if not mentions(text, skill):
        return False
    if skill != 'React':
        return True
    # "react" is usually a verb, so it needs a technical neighbour, like Go and R in the evaluator.
    normal = normalize(text)
    for match in re.finditer(r"(?<![\w+#])react(?:\.?js)?(?![\w+#])", normal, re.I):
        if '.' in match[0] or 'js' in match[0].casefold() or REACT_CONTEXT.search(normal[:match.start()]) \
                or (REACT_AFTER.match(normal[match.end():]) and normal[match.end():].strip(' .;') != ''):
            return True
    return False


def skill_list(text: str) -> set[str]:
    # The entire value must be a list of known skills, never instructions, years or prose.
    parts = re.split(r"\s*(?:,|/|\band\b|&)\s*", text, flags=re.I)
    skills = set()
    for part in parts:
        canonical = next((key for key, aliases in FIT_SKILLS.items()
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


def section_level(job: str, span: SourceSpan) -> str | None:
    # The nearest heading above a line governs it; an unrelated heading clears the requirement context.
    for line in reversed(job[:span.start].split('\n')[:-1]):
        stripped = line.strip().strip('#*_ ').strip()
        if not stripped or len(stripped) > 60:
            continue
        if line.lstrip().startswith('#') or stripped.endswith(':') or HEADING_REQUIRED.fullmatch(stripped):
            if HEADING_PREFERRED.search(stripped):
                return 'preferred'
            return 'required' if HEADING_REQUIRED.search(stripped) else None
    return None


def skill_window(clause: str, skill: str) -> str:
    for alias in FIT_SKILLS[skill]:
        match = re.search(rf"(?<![\w+#]){re.escape(alias)}(?![\w+#])", clause, re.I)
        if match:
            return clause[max(0, match.start() - WINDOW):match.end() + WINDOW]
    return clause


def is_title(job: str, span: SourceSpan) -> bool:
    # ground_analysis places the title on the first line, followed by the description.
    first, separator, _ = job.partition('\n')
    return bool(separator) and span.start == 0 and span.end == len(first) and len(first) <= 80 and first[-1] not in '.!?:'


def long_qualified_sentence(text: str, span: SourceSpan) -> bool:
    # Look outside a window only within its original sentence, not the whole posting.
    line_start = text.rfind('\n', 0, span.start) + 1
    line_end = text.find('\n', span.end)
    line = text[line_start:line_end if line_end >= 0 else len(text)]
    for match in re.finditer(r"\S.*?(?:[.!?](?=\s|$)|$)", line):
        if line_start + match.start() <= span.start and span.end <= line_start + match.end():
            return len(match[0]) > 600 and bool(NEGATION.search(match[0]))
    return False


def requirement_level(job: str, span: SourceSpan, skill: str) -> str:
    if long_qualified_sentence(job, span):
        return 'unclear'
    quote = normalize(span.quote)
    clause = next((part for part in re.split(r";|\b(?:but|while|though|although)\b", quote, flags=re.I)
                   if fit_mentions(part, skill)), quote)
    segment = next((part for part in clause.split(',') if fit_mentions(part, skill)), clause)
    # Real postings are often one long line, so cues only count near the skill.
    nearby = skill_window(clause, skill)
    if quote.endswith('?'):
        return 'unclear'
    # "Python (optional Java or Scala)": a parenthetical about other skills does not qualify this one.
    def about_others(group):
        return (not fit_mentions(group, skill)
                and any(fit_mentions(group, other) for other in FIT_SKILLS if other != skill))
    own = re.sub(r"\(([^)]*)\)", lambda group: ' ' if about_others(group[1]) else group[0], segment)
    if NOT_REQUIRED.search(own):
        return 'not_required'
    if PREFERRED.search(own):
        return 'preferred'
    context = section_level(job, span)
    listed = any(fit_mentions(group, skill) and re.search(r"[,/]", group)
                 for group in re.findall(r"\(([^)]*)\)", clause))
    if (EXAMPLE.search(nearby) or listed) and (REQUIRED.search(nearby) or context == 'required'):
        return 'example'
    if re.search(r"\bor\b", nearby, re.I) or NEGATION.search(nearby):
        return 'unclear'
    if REQUIRED.search(nearby):
        return 'required'
    if context:
        return context
    return 'title' if is_title(job, span) else 'unclear'


def job_levels(job: str, skill: str) -> set[str]:
    return {requirement_level(job, span, skill) for span in spans(job, 'job') if fit_mentions(span.quote, skill)}


def with_wrapped_line(profile: str, span: SourceSpan) -> str:
    # A wrapped sentence can split its negation from its object, so include an unterminated previous line.
    start = profile.rfind('\n', 0, span.start)
    previous = profile[profile.rfind('\n', 0, start) + 1:start].strip() if start >= 0 else ''
    if span.start != start + 1 or not previous or previous[-1] in '.!?:' or previous[0] in '#-*' or ':' in previous:
        return span.quote
    return previous + ' ' + span.quote


def limited(context: str, skill: str) -> bool:
    return any(fit_mentions(part, skill) and NEGATION.search(part)
               for part in re.split(r",|;|\b(?:but|however)\b", context, flags=re.I))


def limitations(profile: str, skill: str) -> list[SourceSpan]:
    # Direct statements, plus "never deployed it" directly after a sentence naming this skill alone.
    result, items = [], spans(profile, 'profile')
    for index, span in enumerate(items):
        if fit_mentions(span.quote, skill):
            if limited(with_wrapped_line(profile, span), skill):
                result.append(span)
        elif index and NEGATION.search(span.quote) and PRONOUN.search(span.quote) \
                and not any(fit_mentions(span.quote, other) for other in FIT_SKILLS):
            named = [other for other in FIT_SKILLS if fit_mentions(items[index - 1].quote, other)]
            if named == [skill]:
                result.append(span)
    return result


def ambiguous_qualifier(profile: str, skill: str) -> bool:
    # "Skills: A, B. Never deployed it." may qualify either one, which blocks a strength without stating a limit.
    items = spans(profile, 'profile')
    for index, span in enumerate(items):
        if index and fit_mentions(items[index - 1].quote, skill) and NEGATION.search(span.quote) \
                and PRONOUN.search(span.quote) and not any(fit_mentions(span.quote, other) for other in FIT_SKILLS):
            return True
    return False


def supports_skill(quote: str, skill: str) -> bool:
    if skill in declared_skills(quote, 'profile'):
        return True
    return fit_mentions(quote, skill) and bool(WORK.search(quote)) and not TOY.search(quote)


def support_level(kind: str, quote: str | None, skill: str) -> str:
    if kind == 'strength':
        return 'partially_demonstrated' if skill in declared_skills(quote or '', 'profile') else 'demonstrated'
    return {'not_demonstrated': 'not_demonstrated_in_profile', 'explicit_limitation': 'explicit_limitation',
            'shared_mention': 'uncertain', 'uncertain_requirement': 'uncertain'}[kind]


def validate(draft: ClaimDraft, job: str, profile: str,
             job_span: SourceSpan | None, profile_span: SourceSpan | None) -> Claim:
    verdict, reason, level = 'insufficient_evidence', 'Missing, stale, mismatched or wrong-source citation.', None
    job_ok = resolve(job_span, 'job', job) and draft.job_excerpt_id == job_span.excerpt_id
    profile_ok = (resolve(profile_span, 'profile', profile)
                  and draft.profile_excerpt_id == profile_span.excerpt_id)
    if draft.skill not in FIT_SKILLS:
        reason = 'Skill is outside the controlled vocabulary; no duration or arbitrary assertions allowed.'
    elif job_ok and fit_mentions(job_span.quote, draft.skill):
        level = requirement_level(job, job_span, draft.skill)
        levels = job_levels(job, draft.skill)
        if draft.kind == 'uncertain_requirement':
            if draft.profile_excerpt_id is not None or profile_span is not None:
                reason = 'A posting inconsistency must not carry a profile assertion.'
            elif {'required', 'not_required'} <= levels:
                verdict, reason = 'supported', 'The posting both requires this and says it is not required.'
            else:
                reason = 'The posting is not inconsistent about this skill.'
        elif {'required', 'not_required'} <= levels:
            reason = 'The posting is inconsistent about this requirement.'
        elif draft.kind == 'not_demonstrated':
            if draft.profile_excerpt_id is not None or profile_span is not None:
                reason = 'Evidence-gap claims must not carry a profile assertion.'
            elif level not in STRONG:
                reason = 'A mention is not a verified advertised requirement.'
            elif not profile.strip():
                reason = 'No profile was supplied, so absence cannot be assessed.'
            elif fit_mentions(profile, draft.skill):
                verdict, reason = 'contradicted', 'Profile mentions this skill; an absence claim is unsafe.'
            else:
                verdict, reason = 'supported', 'Verified requirement; skill not mentioned in supplied profile.'
        elif draft.kind == 'explicit_limitation':
            if not profile_ok or profile_span not in limitations(profile, draft.skill):
                reason = 'Citation does not state a limitation for this skill.'
            elif level not in STRONG:
                reason = 'A mention is not a verified advertised requirement.'
            else:
                verdict, reason = 'supported', 'Profile text qualifies or limits this advertised skill.'
        elif profile_ok and fit_mentions(profile_span.quote, draft.skill):
            if (limited(with_wrapped_line(profile, profile_span), draft.skill) or NEGATION.search(job_span.quote)
                    or limitations(profile, draft.skill) or long_qualified_sentence(profile, profile_span)):
                reason = 'Negation or qualification requires manual review.'
            elif draft.kind == 'shared_mention':
                verdict, reason = 'supported', 'Only shared textual mentions are established; no proficiency claim.'
            elif ambiguous_qualifier(profile, draft.skill):
                reason = 'A nearby qualification may apply to this skill.'
            elif level in STRONG and supports_skill(profile_span.quote, draft.skill):
                verdict, reason = 'supported', 'Advertised skill backed by a profile declaration or work statement.'
            else:
                reason = 'Mentions alone cannot establish a strength or proficiency.'
    quote = profile_span.quote if profile_span else None
    return Claim(**draft.model_dump(), status='passed_checks' if verdict == 'supported' else 'flagged',
                 verdict=verdict, reason=reason, job_span=job_span, profile_span=profile_span,
                 requirement=level, support=support_level(draft.kind, quote, draft.skill))


def build(posting_id: int, job: str, profile: str, model: str = ENGINE_VERSION) -> Briefing:
    jobs, profiles = spans(job, 'job'), spans(profile, 'profile')
    claims = []
    for skill in FIT_SKILLS:
        job_candidates = [span for span in jobs if fit_mentions(span.quote, skill)]
        if not job_candidates:
            continue
        levels = {id(span): requirement_level(job, span, skill) for span in job_candidates}
        by_level = lambda wanted: next((span for span in job_candidates if levels[id(span)] == wanted), None)
        strong = by_level('required') or by_level('title') or by_level('preferred') or by_level('example')
        profile_candidates = [span for span in profiles if fit_mentions(span.quote, skill)
                              and not limited(with_wrapped_line(profile, span), skill)
                              and not long_qualified_sentence(profile, span)]
        supporting = next((span for span in profile_candidates if supports_skill(span.quote, skill)), None)
        limits = limitations(profile, skill)
        if by_level('required') and by_level('not_required'):
            kind, job_span, profile_span = 'uncertain_requirement', by_level('required'), None
        elif limits:
            if not strong:
                continue
            kind, job_span, profile_span = 'explicit_limitation', strong, limits[0]
        else:
            job_span = strong or next((span for span in job_candidates if not NEGATION.search(span.quote)), None)
            profile_span = supporting or next(iter(profile_candidates), None)
            if job_span is None:
                continue
            if profile_span is not None:
                kind = 'strength' if strong and supporting and not ambiguous_qualifier(profile, skill) else 'shared_mention'
            elif strong and profile.strip() and not fit_mentions(profile, skill):
                kind = 'not_demonstrated'
            else:
                continue
        draft = ClaimDraft(kind=kind, skill=skill, job_excerpt_id=job_span.excerpt_id,
                           profile_excerpt_id=profile_span.excerpt_id if profile_span else None)
        claims.append(validate(draft, job, profile, job_span, profile_span))
    return Briefing(packet=InputPacket(posting_id=posting_id, job_snapshot_id=version(job),
                                      profile_version=version(profile), model=ENGINE_VERSION),
                    engine_version=ENGINE_VERSION, claims=claims)


def render(briefing: Briefing, job: str, profile: str) -> str:
    # Revalidate at the presentation boundary: neither status nor model-supplied labels are proof.
    if (briefing.packet.job_snapshot_id != version(job)
            or briefing.packet.profile_version != version(profile)
            or briefing.engine_version != ENGINE_VERSION
            or briefing.packet.model != ENGINE_VERSION):
        return FALLBACK
    groups = {}
    for claim in briefing.claims:
        checked = validate(ClaimDraft(**{key: getattr(claim, key) for key in ClaimDraft.model_fields}),
                           job, profile, claim.job_span, claim.profile_span)
        if checked.verdict != 'supported':
            continue
        # A strength's wording only separates preferred; a gap's wording also separates weaker asks.
        separate = ('preferred',) if checked.kind == 'strength' else ('preferred', 'example', 'title')
        key = (checked.kind, checked.requirement if checked.requirement in separate else None,
               checked.support if checked.kind == 'strength' else None)
        if checked.skill not in groups.setdefault(key, []):
            groups[key].append(checked.skill)
    templates = (
        (('strength', None, 'demonstrated'), 'Profile describes work with skills requested by the posting: {}.'),
        (('strength', None, 'partially_demonstrated'), 'Profile lists skills requested by the posting: {}.'),
        (('strength', 'preferred', 'demonstrated'), 'Profile describes work with skills the posting prefers: {}.'),
        (('strength', 'preferred', 'partially_demonstrated'), 'Profile lists skills the posting prefers: {}.'),
        (('shared_mention', None, None), 'Posting and profile both mention {}; proficiency and requirement coverage are unverified.'),
        (('shared_mention', 'preferred', None), 'Posting prefers and profile mentions {}; proficiency is unverified.'),
        (('explicit_limitation', None, None), 'Profile states a limitation or qualification for requested skills: {}.'),
        (('explicit_limitation', 'preferred', None), 'Profile states a limitation or qualification for preferred skills: {}.'),
        (('not_demonstrated', None, None), 'Advertised requirements not demonstrated in the supplied profile: {}; this does not establish inability.'),
        (('not_demonstrated', 'preferred', None), 'Preferred skills not demonstrated in the supplied profile: {}; this does not establish inability.'),
        (('not_demonstrated', 'title', None), 'The role title names skills not demonstrated in the supplied profile: {}; this does not establish inability.'),
        (('not_demonstrated', 'example', None), 'The posting gives these as examples of what it asks for, and the supplied profile does not mention them: {}; other tools may satisfy this.'),
        (('uncertain_requirement', None, None), 'The posting is inconsistent about whether it requires: {}.'),
    )
    sentences = [template.format(', '.join(groups[key])) for key, template in templates if key in groups]
    return ' '.join(sentences) or FALLBACK
