# Offline paired fit evaluation; ROOT holds historical recordings and synthetic faults stay separately counted.
from collections import Counter

from evals.compare import adversarial_pass, convert
from evals.data import ROOT, job_text, load
from jagent.analysis import Analysis, ground_analysis, job_input, parse_analysis
from jagent.briefing.evidence import check, job_excerpts, profile_excerpts
from jagent.briefing.grounded import FALLBACK


def evaluate(root=ROOT):
    profile = (root / 'profile.md').read_text().split('\n', 1)[1]
    counts = Counter()
    rows = []
    for path in sorted((root / 'postings').glob('*.fixture')):
        posting = load(path)
        output = load(root / 'outputs' / path.name)
        jobs, profiles = job_excerpts(job_text(posting)), profile_excerpts(profile)
        drafts, _ = convert(output, jobs, profiles)
        labels = load(root / 'labels' / path.name)
        counts['stored_human_labels'] += len(labels['claims'])
        counts['pending_claim_labels'] += len(drafts) - len(labels['claims'])
        counts['reviewed_cases'] += labels['missed_requirements'] is not None
        counts['legacy_claims'] += len(drafts)
        counts['legacy_verified'] += sum(check(draft, jobs, profiles, profile).status == 'passed_checks'
                                          for draft in drafts)
        result = ground_analysis(parse_analysis(output['content']), job_input(posting), profile,
                                 posting['id'], output['model'])
        briefing = result._briefing
        supported = [claim for claim in briefing.claims if claim.verdict == 'supported']
        counts['adapted_claims'] += len(supported)
        counts['adapted_with_citations'] += sum(claim.job_span is not None and
            (claim.profile_span is not None or claim.kind == 'not_demonstrated') for claim in supported)
        counts['adapted_gap_claims'] += sum(claim.kind == 'not_demonstrated' for claim in supported)
        counts['adapted_flagged'] += sum(claim.verdict != 'supported' for claim in briefing.claims)
        counts['adapted_abstentions'] += result.explanation == FALLBACK
        counts['cases'] += 1
        before = after = None
        if posting.get('adversarial'):
            before = adversarial_pass(posting, output, drafts, jobs, profiles, profile)
            # Empty legacy citation maps deliberately check that final text leaks no raw profile spans.
            after = adversarial_pass(posting, {'analysis': {'explanation': result.explanation},
                                               'content': result.explanation}, [], {}, {}, profile)
            counts['adversarial_before_pass'] += before
            counts['adversarial_after_pass'] += after
            counts['adversarial_cases'] += 1
        rows.append((path.stem, len(drafts), len(supported), len(labels['claims']), before, after))
    print('Offline historical replay; no model calls; evidence coverage is not human correctness.')
    print('Metric | Value')
    for name, value in sorted(counts.items()):
        print(f'{name} | {value}')
    print('Human precision after adaptation | N/A (new claims are not human labeled)')
    print('Factual contradiction rate | N/A (no complete human labels)')
    print('New inference latency/cost/tokens | not measured')
    print('\nCase | Legacy claims | Adapted claims | Stored labels | Attack before/after')
    for case_id, before_n, after_n, labels_n, before, after in rows:
        attacks = '—' if before is None else f'{"PASS" if before else "FAIL"}/{"PASS" if after else "FAIL"}'
        print(f'{case_id} | {before_n} | {after_n} | {labels_n} | {attacks}')

    seeded = load(root / 'grounded' / 'faults.fixture')
    removed = 0
    for case in seeded['cases']:
        candidate = Analysis(seniority='unknown', required_languages=None, employment_types=None,
                             salary=None, evidence={}, explanation=case['narrative'])
        result = ground_analysis(candidate, {'description': seeded['job']}, seeded['profile'], 0, 'canned')
        removed += not any(term.casefold() in result.explanation.casefold() for term in case['forbidden'])
    print(f'\nSynthetic canned faulty narratives removed | {removed}/{len(seeded["cases"])}')
    return dict(counts), removed


if __name__ == '__main__':
    evaluate()
