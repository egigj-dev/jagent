# Offline recommendation preview; candidates pair snapshots with assessments, filters remain authoritative.
from datetime import datetime
from math import isfinite

from jagent.briefing.assessment import Assessment, current
from jagent.filters import passes_filters
from jagent.runner import make_dedupe_key


def duplicate_key(posting):
    # Reuse collection identity but require exact role spelling and location agreement.
    # Existing collector punctuation normalization alone can conflate C# and C++.
    identity = make_dedupe_key(posting.get('company'), posting.get('title'))
    if not identity or not (posting.get('title') or '').strip() or not posting.get('locations'):
        return ('unique', posting['id'])
    return (identity, ' '.join(posting['title'].casefold().split()),
            tuple(sorted(location.strip().casefold() for location in posting['locations'])))


def preview(candidates: list[tuple[dict, str, Assessment]], profile: str, filters: dict, now: datetime):
    if now.tzinfo is None:
        raise ValueError('Preview time must be timezone aware.')
    rows = []
    seen_ids = set()
    for posting, job, assessment in candidates:
        posting_id = posting['id']
        if posting_id in seen_ids:
            raise ValueError('Duplicate candidate ID.')
        seen_ids.add(posting_id)
        reasons = []
        valid = current(assessment, posting_id, job, profile)
        metadata = dict(title=None, locations=None, remote=None, expires_at=None,
                        posted_at=None, first_seen=None)
        metadata.update(posting)
        dates = [metadata[key] for key in ('expires_at', 'posted_at', 'first_seen') if metadata[key] is not None]
        dates_valid = all(isinstance(date, datetime) and date.tzinfo is not None for date in dates)
        active = dates_valid and passes_filters(metadata, filters, now)
        # Explicit queue membership is required: preview cannot broaden collection selection.
        eligible = active and posting.get('queued') is True and posting.get('action') in (None, 'later') and valid
        if not active:
            reasons.append('Existing activity/location/title filters exclude this posting.')
        if posting.get('queued') is not True:
            reasons.append('Not selected by the existing queue.')
        if posting.get('action') not in (None, 'later'):
            reasons.append('Existing review excludes this posting.')
        if not valid:
            reasons.append('Assessment is stale or invalid.')
        prior = posting.get('similarity')
        prior = float(prior) if isinstance(prior, (int, float)) and isfinite(prior) else None
        score = (max(0, min(1, prior)) * 100) if prior is not None else 0.0
        claims = [claim for claim in assessment.briefing.claims if claim.verdict == 'supported'] if valid else []
        # Required strengths carry more weight than preferred; examples/title/mentions never incur gaps.
        for claim in claims:
            delta = 0
            if claim.requirement == 'required':
                if claim.kind == 'strength':
                    delta = 4 if claim.support == 'demonstrated' else 2
                elif claim.kind in ('not_demonstrated', 'explicit_limitation'):
                    delta = -4
            elif claim.requirement == 'preferred' and claim.kind == 'strength':
                delta = 1
            if delta:
                score += delta
                reasons.append(f'{claim.skill}: {claim.support} ({delta:+d}; {claim.job_excerpt_id}).')
        constraints = sorted({item.kind for item in assessment.constraints}) if valid else []
        if constraints:
            reasons.append('Constraints remain unverified: ' + ', '.join(constraints) + '.')
        rows.append(dict(posting_id=posting_id, eligible=eligible, prior_score=prior,
                         preview_score=round(score, 4), reasons=reasons, group=None,
                         prior_rank=None, preview_rank=None, evidence=[c.job_excerpt_id for c in claims],
                         _key=duplicate_key(posting), _assessment=assessment, _job=job))
    baseline = sorted(rows, key=lambda row: (-(row['prior_score'] if row['prior_score'] is not None else -1), row['posting_id']))
    for index, row in enumerate(baseline, 1):
        row['prior_rank'] = index
    ordered = sorted(rows, key=lambda row: (-row['preview_score'], row['posting_id']))
    groups = {}
    rank = 0
    # Excluded duplicates never suppress an eligible recommendation.
    for row in ordered:
        if not row['eligible']:
            continue
        key = row['_key']
        row['group'] = groups.setdefault(key, row['posting_id'])
        if row['group'] != row['posting_id']:
            row['reasons'].append('Duplicate of candidate ' + str(row['group']) + '.')
            continue
        rank += 1
        row['preview_rank'] = rank
    return sorted(rows, key=lambda row: (row['preview_rank'] or len(rows) + 1, row['posting_id']))


def public_rows(rows):
    # Never serialize internal profile citations or raw posting prose to reports/logs.
    return [{key: value for key, value in row.items() if not key.startswith('_')} for row in rows]
