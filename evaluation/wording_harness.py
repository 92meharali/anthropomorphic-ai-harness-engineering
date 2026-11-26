"""Prepare and analyze a blinded wording-pair study using saved scores."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import random

from .data import digest, read_jsonl, write_json, write_jsonl
from .run import plan

MODEL = 'gpt-6.2-sol'
CHOICES = ('A', 'B', 'tie', 'cannot_judge')
CUE_CHOICES = ('A', 'B', 'both', 'neither', 'cannot_judge')
FILES = ('oa_inputs.jsonl', 'review_packet.jsonl', 'pair_key.jsonl', 'protocol.json')


def indexed(rows, field):
    result = {}
    for row in rows:
        key = row[field]
        if not isinstance(key, str) or not key.strip() or key in result:
            raise ValueError(f'Missing or duplicate {field}')
        result[key] = row
    return result


def prepare(source, protocol, directory, seed, *, separate_families=False):
    pairs = list(indexed(read_jsonl(source), 'pair_id').values())
    if not pairs:
        raise ValueError('At least one pair is required')
    protocol_bytes = protocol.read_bytes()
    if set(json.loads(protocol_bytes)['dimensions']) != {'OA'}:
        raise ValueError('Expected the OA-only protocol')

    rng = random.Random(seed)
    for _ in range(1000):
        rng.shuffle(pairs)
        if not separate_families or all(a['prompt_group_id'] != b['prompt_group_id']
                                        for a, b in zip(pairs, pairs[1:])):
            break
    else:
        raise ValueError('Could not separate sibling contexts')
    packet, inputs, key = [], [], []
    prompt_groups = {}
    for number, pair in enumerate(pairs, 1):
        for field in ('prompt_group_id', 'cue', 'prompt', 'original', 'edited'):
            if not isinstance(pair[field], str) or not pair[field].strip():
                raise ValueError(f'Missing or empty {field}')
        if pair['original'].strip() == pair['edited'].strip():
            raise ValueError('Original and edited answers must differ')
        normalized = ' '.join(pair['prompt'].casefold().split())
        if prompt_groups.setdefault(normalized, pair['prompt_group_id']) != pair['prompt_group_id']:
            raise ValueError('Identical prompts must share a prompt group')
        review_id = f'W{number:04d}'
        versions = ['original', 'edited']
        rng.shuffle(versions)
        review = {'review_id': review_id, 'prompt': pair['prompt']}
        for position, version in zip(('A', 'B'), versions):
            review[position] = pair[version]
            inputs.append({'item_id': f'{review_id}-{position}',
                           'prompt': pair['prompt'], 'response': pair[version]})
        review['pair_sha256'] = digest(json.dumps(review, sort_keys=True, ensure_ascii=False))
        packet.append(review)
        key.append({'review_id': review_id, 'pair_id': pair['pair_id'],
                    'prompt_group_id': pair['prompt_group_id'], 'cue': pair['cue'],
                    'A': versions[0], 'B': versions[1]})

    directory.mkdir(parents=True, exist_ok=False)
    write_jsonl(directory / 'oa_inputs.jsonl', inputs)
    write_jsonl(directory / 'review_packet.jsonl', packet)
    write_jsonl(directory / 'pair_key.jsonl', key)
    (directory / 'protocol.json').write_bytes(protocol_bytes)
    write_json(directory / 'manifest.json', {
        'version': 1, 'seed': seed, 'model': MODEL, 'pairs': len(pairs),
        'humt_baseline': 'prefer_lower', 'oa_baseline': 'prefer_higher',
        'source_sha256': digest(source.read_bytes()),
        **({'separate_families': True} if separate_families else {}),
        'sha256': {name: digest((directory / name).read_bytes()) for name in FILES},
    })


def signed_choice(a, b, lower=False):
    if a is None or b is None:
        return 'unresolved'
    if a == b:
        return 'tie'
    return 'A' if (a < b if lower else a > b) else 'B'


def human_choice(votes):
    counts = Counter(votes)
    for choice in ('A', 'B', 'tie'):
        if counts[choice] >= 2:
            return choice
    return 'unresolved'


def compare(rows):
    common = [r for r in rows if 'unresolved' not in (r['human'], r['humt'], r['oa'])]
    outcomes = Counter()
    for row in common:
        oa_match = row['oa'] == row['human']
        humt_match = row['humt'] == row['human']
        outcomes['oa_correct' if oa_match else 'oa_wrong'] += 1
        outcomes['humt_correct' if humt_match else 'humt_wrong'] += 1
        if oa_match != humt_match:
            outcomes['only_oa_correct' if oa_match else 'only_humt_correct'] += 1
    return {'pairs': len(rows), 'common_comparable_pairs': len(common),
            'comparable_prompt_groups': len({r['prompt_group_id'] for r in common}),
            'human_choices': dict(Counter(r['human'] for r in rows)),
            'oa_choices': dict(Counter(r['oa'] for r in rows)),
            'humt_choices': dict(Counter(r['humt'] for r in rows)),
            'agreement_counts': dict(outcomes)}


def analyze(directory, oa_path, humt_path, reviewer_paths):
    manifest = json.loads((directory / 'manifest.json').read_text())
    if manifest.get('version') != 1 or manifest.get('model') != MODEL:
        raise ValueError('Unsupported study manifest')
    for name in FILES:
        if digest((directory / name).read_bytes()) != manifest['sha256'][name]:
            raise ValueError(f'Frozen file changed: {name}')

    inputs = read_jsonl(directory / 'oa_inputs.jsonl')
    case_inputs = indexed(inputs, 'item_id')
    protocol = json.loads((directory / 'protocol.json').read_text())
    jobs = indexed(plan(inputs, protocol, ('openai',), {'openai': MODEL}), 'item_id')
    oa = indexed(read_jsonl(oa_path), 'item_id')
    humt = indexed(read_jsonl(humt_path), 'item_id')
    key = indexed(read_jsonl(directory / 'pair_key.jsonl'), 'review_id')
    packet = indexed(read_jsonl(directory / 'review_packet.jsonl'), 'review_id')
    if len({path.resolve() for path in reviewer_paths}) != 3:
        raise ValueError('Supply three different reviewer files')
    reviews = [indexed(read_jsonl(path), 'review_id') for path in reviewer_paths]
    if set(oa) - set(jobs) or set(humt) - set(jobs):
        raise ValueError('Unexpected scorer item ID')
    if any(set(review) != set(key) for review in reviews):
        raise ValueError('Each reviewer must cover the frozen packet')

    for item_id, score in oa.items():
        if score.get('job_id') != jobs[item_id]['job_id'] or score.get('request') != jobs[item_id]['request']:
            raise ValueError(f'OA response does not match its frozen request: {item_id}')
        if score['status'] == 'ok' and (type(score['rating']) is not int or score['rating'] not in range(1, 6)):
            raise ValueError(f'Invalid OA rating: {item_id}')
    for item_id, score in humt.items():
        if score.get('response_sha256') != digest(case_inputs[item_id]['response']):
            raise ValueError(f'HumT response hash mismatch: {item_id}')
        value = score['humt']
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
            raise ValueError(f'Invalid HumT score: {item_id}')

    comparisons = []
    for review_id, pair in key.items():
        ballots = [review[review_id] for review in reviews]
        votes = [b['preference'] for b in ballots]
        cue_votes = [b['cue_needs_correction'] for b in ballots]
        preservation = [b['content_preserved'] for b in ballots]
        if any(b.get('pair_sha256') != packet[review_id]['pair_sha256'] for b in ballots):
            raise ValueError(f'Reviewer ballot does not match frozen pair: {review_id}')
        if (any(vote not in CHOICES for vote in votes)
                or any(vote not in CUE_CHOICES for vote in cue_votes)
                or any(value is not None and type(value) is not bool for value in preservation)):
            raise ValueError(f'Invalid reviewer response: {review_id}')
        oa_values, humt_values = [], []
        for option in ('A', 'B'):
            item = f'{review_id}-{option}'
            score = oa.get(item, {})
            oa_values.append(score.get('rating') if score.get('status') == 'ok' else None)
            humt_values.append(humt.get(item, {}).get('humt'))
        comparisons.append({
            **pair, 'human_votes': votes, 'content_preservation_votes': preservation,
            'cue_correction_votes': cue_votes,
            'content_preserved': preservation.count(True) >= 2,
            'human': human_choice(votes), 'oa': signed_choice(*oa_values),
            'humt': signed_choice(*humt_values, lower=True),
            'oa_scores': oa_values, 'humt_scores': humt_values,
        })
    return {
        'rules': {'human': 'two of three votes', 'oa': 'prefer higher OA',
                  'humt': 'prefer lower HumT', 'equal_scores': 'tie'},
        'sha256': {role: digest(path.read_bytes()) for role, path in (
            ('manifest', directory / 'manifest.json'), ('oa', oa_path), ('humt', humt_path),
            *((f'reviewer_{i}', path) for i, path in enumerate(reviewer_paths, 1)),
        )},
        'all_pairs': compare(comparisons),
        'content_preserved_pairs': compare([r for r in comparisons if r['content_preserved']]),
        'by_cue': {cue: compare([r for r in comparisons if r['cue'] == cue])
                   for cue in sorted({r['cue'] for r in comparisons})},
        'pairs': comparisons,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    setup = commands.add_parser('prepare')
    setup.add_argument('--pairs', type=Path, required=True)
    setup.add_argument('--protocol', type=Path, required=True)
    setup.add_argument('--study', type=Path, required=True)
    setup.add_argument('--seed', type=int, default=20261123)
    report = commands.add_parser('analyze')
    report.add_argument('--study', type=Path, required=True)
    report.add_argument('--oa', type=Path, required=True)
    report.add_argument('--humt', type=Path, required=True)
    report.add_argument('--reviewers', type=Path, nargs=3, required=True)
    report.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'prepare':
            prepare(args.pairs, args.protocol, args.study, args.seed)
            print(f'Frozen study prepared at {args.study}')
        else:
            result = analyze(args.study, args.oa, args.humt, args.reviewers)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open('x') as stream:
                json.dump(result, stream, ensure_ascii=False, indent=2)
                stream.write('\n')
            print(json.dumps(result['all_pairs'], indent=2))
    except (KeyError, TypeError, ValueError, OSError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    main()
