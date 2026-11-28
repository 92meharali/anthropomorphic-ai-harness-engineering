"""Reproduce the frozen paired comparison from sealed Excel ballots."""
import argparse
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
import random

from . import rewrite_freeze as f
from .rewrite_generate import ARMS

COMPONENTS = ('cue_corrected', 'advice_preserved', 'warmth_preserved')
LABEL = {True: 'pass', False: 'fail', None: 'unresolved'}
PAIR_OUTCOMES = {(True, True): 'both_usable', (True, False): 'cue_only',
                 (False, True): 'generic_only', (False, False): 'neither_usable'}


def reviewer_checks(rating, threshold):
    checks = {field: rating[field] for field in COMPONENTS}
    oa = rating['oa']
    checks['oa_pass'] = None if oa is None else oa >= threshold
    values = tuple(checks.values())
    checks['usable'] = False if False in values else None if None in values else True
    return checks


def majority(votes, needed):
    return next((value for value, count in Counter(votes).items()
                 if value is not None and count >= needed), None)


def ratio(n, d):
    return n / d if d else None


def family_interval(families, protocol):
    if len(families) < 2:
        return None
    blocks = [(sum(values), len(values)) for _, values in sorted(families.items())]
    rng = random.Random(protocol['bootstrap_seed'])
    distribution = []
    for _ in range(protocol['bootstrap_draws']):
        sample = rng.choices(blocks, k=len(blocks))
        distribution.append(sum(total for total, _ in sample) / sum(n for _, n in sample))
    distribution.sort()
    return [distribution[int((len(distribution) - 1) * q)] for q in (0.025, 0.975)]


def paired_results(key, ballots, summary, config):
    review = config['review']
    protocol = config['primary_outcome']
    by_case = defaultdict(list)
    for vote in ballots:
        by_case[vote['review_id']].append(vote)

    criteria = {arm: defaultdict(Counter) for arm in ARMS}
    agreement = defaultdict(Counter)
    families = defaultdict(list)
    paired = Counter({arm: 0 for arm in ARMS})
    patterns = Counter({name: 0 for name in (*PAIR_OUTCOMES.values(), 'unresolved')})
    for row in key:
        outcomes = {}
        votes = by_case[row['review_id']]
        if len(votes) != review['reviewers']:
            raise ValueError('Incomplete verified ballot coverage')
        for pos in ('A', 'B'):
            arm = row[pos]
            scores = [reviewer_checks(vote[pos], review['oa_threshold']) for vote in votes]
            for field in (*scores[0], 'oa_exact'):
                values = ([vote[pos]['oa'] for vote in votes] if field == 'oa_exact'
                          else [record[field] for record in scores])
                for left, right in combinations((v for v in values if v is not None), 2):
                    agreement[field]['comparable'] += 1
                    agreement[field]['matches'] += left == right
                if field != 'oa_exact':
                    result = majority(values, review['majority'])
                    criteria[arm][field][LABEL[result]] += 1
                    if field == 'usable':
                        outcomes[arm] = result

        cue, generic = (outcomes[arm] for arm in ARMS)
        patterns[PAIR_OUTCOMES.get((cue, generic), 'unresolved')] += 1
        if cue is not None and generic is not None:
            paired.update({ARMS[0]: int(cue), ARMS[1]: int(generic)})
            families[row['prompt_group_id']].append(int(cue) - int(generic))

    n = len(key) - patterns['unresolved']
    flagged = summary['flagged']
    counts = {arm: criteria[arm]['usable']['pass'] for arm in ARMS}
    return {
        'flagged_drafts': flagged, 'generation_calls': summary['calls'],
        'eligible_pairs': len(key), 'case_ballots': len(ballots),
        'paired_resolved': n, 'resolved_prompt_families': len(families),
        'pairs': patterns,
        'primary': {
            'paired_success': paired, 'rates': {arm: ratio(paired[arm], n) for arm in ARMS},
            'cue_minus_generic': ratio(paired[ARMS[0]] - paired[ARMS[1]], n),
            'interval_95': family_interval(families, protocol),
            'bootstrap_draws': protocol['bootstrap_draws'], 'bootstrap_seed': protocol['bootstrap_seed'],
        },
        'all_flagged_sensitivity': {
            'rates': {arm: ratio(counts[arm], flagged) for arm in ARMS},
            'cue_minus_generic': ratio(counts[ARMS[0]] - counts[ARMS[1]], flagged),
        },
        'criteria': criteria,
        'reviewer_agreement': {field: {**value, 'rate': ratio(value['matches'], value['comparable'])}
                               for field, value in agreement.items()},
        'generation': summary['arms'], 'model_mismatch_pairs': summary['model_mismatch_pairs'],
        'usage_by_stage': summary['usage'],
    }


def report(root, study, run, packet, collection, freeze_sha, packet_sha, collection_sha):
    from .rewrite_blind import verify_collection

    _, _, key, ballots = verify_collection(root, study, run, packet, collection,
                                           freeze_sha, packet_sha, collection_sha)
    config = f.load(study / 'plan.json')['body']['config']
    summary = f.load(run / 'summary.json')
    result = paired_results(key, ballots, summary, config)
    result['input_sha256'] = {
        'freeze': freeze_sha, 'packet': packet_sha, 'ballot_collection': collection_sha,
        'run_status': f.sha((run / 'status.json').read_bytes()),
    }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    paths = ('study', 'run', 'packet', 'collection', 'out')
    for name in paths:
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('freeze', 'packet', 'collection'):
        parser.add_argument(f'--{name}-sha256', required=True)
    args = parser.parse_args()
    study, run, packet, collection, out = (f.private_path(getattr(args, name)) for name in paths)
    result = report(f.ROOT, study, run, packet, collection,
                    args.freeze_sha256, args.packet_sha256, args.collection_sha256)
    out.mkdir(parents=True, mode=0o700)
    f.write(out / 'comparison.json', result)
    print(f'Saved aggregate comparison for {result["paired_resolved"]} resolved pairs.')


if __name__ == '__main__':
    main()
