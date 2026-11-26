"""Prepare blinded generated-rewrite ballots and analyze paired results."""
import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import random

from .data import digest, read_jsonl, write_json, write_jsonl
from .rewrite_study import ARMS, REVIEW_GUIDE, object_hash, verify_run

POSITIONS = ('A', 'B')
FIELDS = ('cue_corrected', 'advice_preserved', 'warmth_preserved', 'oa')
COLUMNS = ('review_id', 'case_sha256', *(f'{p.lower()}_{f}' for p in POSITIONS for f in FIELDS))
DRAWS = 10000


def has_two_answers(result):
    return all(result['rewrites'].get(arm, {}).get('response') is not None for arm in ARMS)


def matching_generator(result):
    a, b = (result['rewrites'][arm]['returned_model'] for arm in ARMS)
    return isinstance(a, str) and bool(a.strip()) and a == b


def packets(drafts, outcomes, seed):
    complete = [(row, result) for row, result in zip(drafts, outcomes)
                if has_two_answers(result) and matching_generator(result)]
    rng = random.Random(seed + 1)
    rng.shuffle(complete)
    first = rng.randrange(2)
    blinded, private = [], []
    for i, (row, result) in enumerate(complete):
        order = ARMS if (i + first) % 2 == 0 else ARMS[::-1]
        case = {'review_id': f'RW{i + 1:04d}', 'visible_history': row['visible_history'],
                'current_user_message': row['current_user_message'], 'original': row['draft'],
                **{pos: result['rewrites'][arm]['response'] for pos, arm in zip(POSITIONS, order)}}
        case['case_sha256'] = object_hash(case)
        blinded.append(case)
        private.append({'review_id': case['review_id'], 'draft_id': row['draft_id'],
                        'prompt_group_id': row['prompt_group_id'], **dict(zip(POSITIONS, order))})
    return blinded, private


def prepare(study, run, out):
    manifest, drafts, outcomes, _ = verify_run(study, run)
    config = manifest['configuration']
    public, key = packets(drafts, outcomes, config['seed'])
    out.mkdir(parents=True, mode=0o700)
    share = out / 'reviewer'
    share.mkdir()
    write_jsonl(out / 'cases.jsonl', public)
    write_jsonl(out / 'key.jsonl', key)
    guide = REVIEW_GUIDE.read_text()
    guide += '\n## Capabilities for this cohort\n\n'
    guide += ''.join(f'- {name.replace("_", " ")}: {str(value).lower()}\n'
                     for name, value in config['capabilities'].items())
    (share / 'guide.md').write_text(guide)
    with (share / 'ratings.csv').open('x', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(COLUMNS)
        writer.writerows([case['review_id'], case['case_sha256'], *[''] * (len(COLUMNS) - 2)]
                         for case in public)
    with (share / 'cases.txt').open('x') as file:
        for case in public:
            file.write(f'{case["review_id"]}\n\n')
            for turn in case['visible_history']:
                file.write(f'Earlier {turn["role"]}: {turn["content"]}\n')
            for heading, field in (('Current user message', 'current_user_message'),
                                   ('Original draft', 'original'), ('Rewrite A', 'A'), ('Rewrite B', 'B')):
                file.write(f'\n{heading}\n{case[field]}\n')
            file.write('\n' + '-' * 60 + '\n\n')
    return len(public)


def ballots(path, cases):
    hashes = {c['review_id']: c['case_sha256'] for c in cases}
    result = {}
    with path.open(encoding='utf-8-sig', newline='') as file:
        rows = csv.DictReader(file)
        if tuple(rows.fieldnames or []) != COLUMNS:
            raise ValueError('Unexpected ballot columns')
        for row in rows:
            rid = row['review_id']
            if (None in row or rid in result or rid not in hashes
                    or row['case_sha256'] != hashes[rid]):
                raise ValueError('Unexpected, duplicate or changed ballot case')
            ratings = {}
            for position in POSITIONS:
                ratings[position] = {}
                for field in FIELDS:
                    value = (row[f'{position.lower()}_{field}'] or '').strip().casefold()
                    if value == 'uncertain':
                        ratings[position][field] = None
                    elif field == 'oa' and value in ('1', '2', '3', '4', '5'):
                        ratings[position][field] = int(value)
                    elif field != 'oa' and value in ('yes', 'no'):
                        ratings[position][field] = value == 'yes'
                    else:
                        raise ValueError(f'Missing or invalid {position} {field} rating for {rid}')
            result[rid] = ratings
    if result.keys() != hashes.keys():
        raise ValueError('Ballot does not cover the full blinded packet')
    return result


def majority(votes):
    return next((value for value, count in Counter(votes).items() if value is not None and count >= 2), None)


def outcomes_for(rating):
    oa = rating['oa']
    checks = {name: rating[name] for name in FIELDS if name != 'oa'}
    checks['oa_pass'] = oa >= 4 if oa is not None else None
    values = checks.values()
    checks['usable_correction'] = False if False in values else None if None in values else True
    return checks


def paired_difference(groups, seed):
    blocks = [(sum(values), len(values)) for values in groups.values()]
    if not blocks:
        return {'cases': 0, 'families': 0, 'difference': None, 'interval_95': None}
    count = sum(n for _, n in blocks)
    point = sum(total for total, _ in blocks) / count
    interval = None
    if len(blocks) >= 2:
        rng = random.Random(seed + 2)
        draws = []
        for _ in range(DRAWS):
            draw = rng.choices(blocks, k=len(blocks))
            draws.append(sum(total for total, _ in draw) / sum(n for _, n in draw))
        draws.sort()
        interval = [draws[int((DRAWS - 1) * q)] for q in (0.025, 0.975)]
    return {'cases': count, 'families': len(blocks), 'difference': point, 'interval_95': interval}


def summarize(study, run, packet, paths, review_note=None):
    manifest, drafts, outcomes, logs = verify_run(study, run)
    seed = manifest['configuration']['seed']
    cases, key = packets(drafts, outcomes, seed)
    if cases != read_jsonl(packet / 'cases.jsonl') or key != read_jsonl(packet / 'key.jsonl'):
        raise ValueError('Review packet differs from the replayed run')
    if len(paths) != (3 if cases else 0) or len({p.resolve() for p in paths}) != len(paths):
        raise ValueError('Supply three separate reviewer ballots for a nonempty packet')
    votes = [ballots(path, cases) for path in paths]
    screened = Counter(o['assessment']['classification'] for o in outcomes)
    generation = {arm: Counter() for arm in ARMS}
    for outcome in outcomes:
        for arm, result in outcome['rewrites'].items():
            state = 'failed' if result['response'] is None else 'changed' if result['changed'] else 'unchanged'
            generation[arm][state] += 1
    per_arm = {arm: defaultdict(Counter) for arm in ARMS}
    comparable_success = Counter({arm: 0 for arm in ARMS})
    groups = defaultdict(list)
    for case in key:
        outcomes_by_arm = {}
        for position in POSITIONS:
            arm = case[position]
            assessments = [outcomes_for(ballot[case['review_id']][position]) for ballot in votes]
            for field in assessments[0]:
                vote = majority([assessment[field] for assessment in assessments])
                per_arm[arm][field][{True: 'yes', False: 'no', None: 'unresolved'}[vote]] += 1
                if field == 'usable_correction':
                    outcomes_by_arm[arm] = vote
        if all(value is not None for value in outcomes_by_arm.values()):
            comparable_success.update({arm: int(value) for arm, value in outcomes_by_arm.items()})
            groups[case['prompt_group_id']].append(
                int(outcomes_by_arm['cue_specific']) - int(outcomes_by_arm['generic']))
    usage = defaultdict(Counter)
    for call in logs:
        stat = usage[call['stage']]
        stat['requests'] += 1
        stat['latency_seconds'] += call['latency_seconds']
        token_counts = (call.get('raw') or {}).get('usage') or {}
        stat['requests_without_usage'] += not bool(token_counts)
        for field in ('input_tokens', 'output_tokens'):
            if type(token_counts.get(field)) is int:
                stat[field] += token_counts[field]
    comparison = paired_difference(groups, seed)
    return {
        'drafts': len(drafts), 'families': manifest['configuration']['families'],
        'screening': screened, 'flagged_drafts': screened['correction'], 'generation': generation,
        'both_rewrites': sum(has_two_answers(result) for result in outcomes),
        'blinded_cases': len(cases), 'paired_resolved': comparison['cases'],
        'usable_correction_on_paired_resolved': comparable_success,
        'cue_minus_generic_usable_correction': comparison, 'rating_counts': per_arm,
        'usage_by_stage': usage, 'configuration_sha256': manifest['configuration_sha256'],
        'reviewer_provenance': review_note or 'Independence and blinding unconfirmed',
        'run_status_sha256': digest((run / 'status.json').read_bytes()),
        'ballot_sha256': [digest(path.read_bytes()) for path in paths],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('packet', 'report'):
        sub = commands.add_parser(name)
        for arg in ('study', 'run', 'out'):
            sub.add_argument('--' + arg, type=Path, required=True)
        if name == 'report':
            sub.add_argument('--packet', type=Path, required=True)
            sub.add_argument('--reviewers', type=Path, nargs=3, default=[])
            sub.add_argument('--review-note', help='Coordinator’s record of independent blinded collection')
    args = parser.parse_args()
    if args.command == 'packet':
        count = prepare(args.study, args.run, args.out)
        print(f'Prepared {count} blinded cases with both rewrites.')
        return
    result = summarize(args.study, args.run, args.packet, args.reviewers, args.review_note)
    args.out.mkdir(parents=True, mode=0o700)
    write_json(args.out / 'comparison.json', result)
    print(f'Saved aggregate comparison for {result["paired_resolved"]} paired cases.')


if __name__ == '__main__':
    main()
