# Sample career observations; rows are validated preview recommendations and counts use unique postings.
from collections import defaultdict

from jagent.briefing.assessment import current


def summarize(rows, profile: str):
    selected = [row for row in rows if row['eligible'] and row['preview_rank'] is not None
                and current(row['_assessment'], row['posting_id'], row['_job'], profile)]
    requested, gaps, strengths = defaultdict(dict), defaultdict(dict), defaultdict(dict)
    constraints = defaultdict(set)
    unknown = 0
    for row in selected:
        assessment = row['_assessment']
        found = False
        for claim in assessment.briefing.claims:
            if (claim.verdict != 'supported' or claim.kind == 'uncertain_requirement'
                    or claim.requirement not in ('required', 'preferred', 'example', 'title')):
                continue
            found = True
            evidence = {'posting_id': row['posting_id'], 'excerpt_id': claim.job_excerpt_id,
                        'requirement': claim.requirement}
            requested[claim.skill][row['posting_id']] = evidence
            if claim.kind in ('not_demonstrated', 'explicit_limitation'):
                gaps[claim.skill][row['posting_id']] = evidence
            elif claim.kind == 'strength':
                strengths[claim.skill][row['posting_id']] = evidence
        unknown += not found
        for constraint in assessment.constraints:
            constraints[constraint.kind].add(row['posting_id'])
    def observations(group):
        return [dict(skill=skill, posting_count=len(sources), evidence=list(sources.values()))
                for skill, sources in sorted(group.items(), key=lambda item: (-len(item[1]), item[0]))]
    priorities = []
    for item in observations(gaps)[:4]:
        priorities.append({**item, 'suggestion': 'Review or document experience with ' + item['skill'] +
                           '; consider a small practice project if this aligns with target roles.',
                           'caveat': 'The supplied profile may omit experience; examples and title mentions may not be mandatory.'})
    return dict(scope='Observations in the supplied sample; not a representative market survey.',
                sample_size=len(selected), excluded_or_duplicate=len(rows) - len(selected),
                extraction='deterministic heuristic; source spans resolve, interpretation is not human verified',
                human_verified_requirement_count=None, requested=observations(requested),
                not_demonstrated=observations(gaps), strengths=observations(strengths),
                constraints=[{'kind': kind, 'posting_ids': sorted(ids), 'candidate_coverage': 'unknown'}
                             for kind, ids in sorted(constraints.items())],
                seniority_mismatch='unknown; duration observations do not establish candidate seniority',
                postings_without_classified_requirements=unknown, priorities=priorities)
