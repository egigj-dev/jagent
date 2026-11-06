# Offline integrated demo; ROOT is frozen input, NOW and FILTERS are explicit synthetic preview policy.
import argparse
from datetime import UTC, datetime
import json

from evals.data import ROOT, load
from jagent.analysis import job_input, parse_analysis, ground_analysis
from jagent.briefing.assessment import assess, explanation, put, restore
from jagent.briefing.grounded import render
from jagent.mentor import summarize
from jagent.recommendations import preview, public_rows

NOW = datetime(2026, 10, 30, tzinfo=UTC)
FILTERS = {'countries': ['portugal', 'netherlands', 'germany', 'albania', 'united states', 'remote'],
           'remote_regions': ['europe', 'worldwide'], 'remote_excluded': [], 'exclude_title_keywords': []}


def snapshot(posting):
    job = job_input(posting)
    return '\n'.join([job.get('title') or '', job.get('description') or ''])


def demo():
    profile = (ROOT / 'profile.md').read_text().split('\n', 1)[1]
    store, candidates, comparisons = {}, [], []
    for path in sorted((ROOT / 'postings').glob('*.fixture')):
        posting = load(path)
        posting.update(remote=None, expires_at=None, first_seen=None,
                       posted_at=datetime.fromisoformat(posting['posting_date']) if posting.get('posting_date') else None)
        job = snapshot(posting)
        output = load(ROOT / 'outputs' / path.name)
        value = assess(posting['id'], job, profile, output['model'])
        put(store, value, job, profile)
        restored = restore(store, posting['id'], job, profile)
        assert restored is not None
        candidates.append((posting, job, restored))
        if posting['id'] in (10343, 51827, 900002):
            parsed = parse_analysis(output['content'])
            adapted = ground_analysis(parsed, job_input(posting), profile, posting['id'], output['model'])
            assert adapted._briefing.packet.model == value.engine_version
            comparisons.append(dict(posting_id=posting['id'],
                # Raw narratives are inspectable in the untouched recordings, never copied to logs.
                legacy_recording='evals/fixtures/outputs/' + path.name,
                legacy_narrative=parsed.explanation if posting['id'] != 900002 else '[See frozen recording: contains an injection marker in a rejection.]',
                night1_controlled_template=render(value.briefing, job, profile),
                assessment_explanation=explanation(value, job, profile),
                constraints=[dict(kind=item.kind, minimum_years=item.minimum_years,
                                  excerpt_id=item.job_span.excerpt_id, support=item.support) for item in value.constraints]))
    # Separate invented controls prove useful positive and uncertain paths without human labels.
    for posting_id, title, description in [(910001, 'Python engineer', 'Required: Python.'),
                                            (910002, 'Systems engineer', 'We sometimes use Kubernetes.')]:
        posting = dict(id=posting_id, company='Synthetic example', title=title, description=description,
                       locations=['Remote'], remote=True, posted_at=NOW, first_seen=NOW,
                       expires_at=None, similarity=0.6, queued=True)
        job = snapshot(posting)
        candidates.append((posting, job, assess(posting_id, job, profile)))
    rows = preview(candidates, profile, FILTERS, NOW)
    return dict(engine_version=candidates[0][2].engine_version, frozen_cases=23, synthetic_controls=2,
                policy='Explicit synthetic filters and frozen 2026-10-30 UTC clock; no user settings loaded.',
                comparisons=comparisons, recommendations=public_rows(rows), mentor=summarize(rows, profile))


def main():
    parser = argparse.ArgumentParser(description='Offline B1 → B2 → C preview; no database or network.')
    parser.add_argument('--json', action='store_true', help='Print public report with evidence IDs; no profile prose.')
    args = parser.parse_args()
    report = demo()
    if args.json:
        print(json.dumps(report, indent=2))
        return
    print(f"Offline B1 → B2 → C | {report['engine_version']} | 23 frozen + 2 synthetic controls")
    print(report['policy'])
    for item in report['comparisons']:
        print(f"B1 {item['posting_id']} | {item['assessment_explanation']}")
        print('Constraint evidence | ' + ', '.join(f"{c['kind']} ({c['minimum_years'] if c['minimum_years'] is not None else 'unknown'}): {c['excerpt_id']}" for c in item['constraints']))
    print('ID | eligible | prior rank/score | preview rank/score | duplicate group')
    for row in report['recommendations']:
        print(f"{row['posting_id']} | {row['eligible']} | {row['prior_rank']}/{row['prior_score']} | {row['preview_rank']}/{row['preview_score']} | {row['group']}")
    mentor = report['mentor']
    print(f"C | {mentor['scope']} Sample size: {mentor['sample_size']}.")
    for priority in mentor['priorities']:
        ids = ','.join(str(e['posting_id']) for e in priority['evidence'])
        print(f"Priority | {priority['skill']} | {priority['posting_count']} posting(s): {ids} | {priority['caveat']}")
    print('Counts and ranking are heuristic; human semantic accuracy and relevance gains are unmeasured.')


if __name__ == '__main__':
    main()
