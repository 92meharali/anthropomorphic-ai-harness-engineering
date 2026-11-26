"""Prepare the reserved wording cohort and a separated A/B packet."""
import argparse
from collections import defaultdict
import json
from pathlib import Path

from .data import ROOT, digest, read_jsonl, write_json, write_jsonl
from .wording_harness import indexed, prepare

SEED = 20261126
ALLOCATION_SHA256 = '8637d998194f46399176247b8f2ae74150cb0829ddf8ce0e086b4d37fc648ffd'
DEVELOPMENT_SHA256 = 'e7a131c007c97e1de003f08a61f3744dca9f59c2c92ff4e1bc406c3e382faaa3'
CORPUS = ROOT / 'data/wording_pairs_v1.jsonl'
ALLOCATION = ROOT / 'data/development_split_v1.json'


def canonical_hash(path):
    return digest(path.read_bytes().replace(b'\r\n', b'\n'))


def select(source, split):
    if canonical_hash(split) != ALLOCATION_SHA256:
        raise ValueError('Allocation differs from the approved v1 split')
    spec = json.loads(split.read_text())
    if canonical_hash(source) != spec['source_sha256']:
        raise ValueError('Source does not match the frozen allocation')
    development = {v for group in spec['development_families'].values() for v in group}
    reserved = {v for group in spec['reserved_families'].values() for v in group}
    rows = read_jsonl(source)
    if development & reserved or {r['prompt_group_id'] for r in rows} != development | reserved:
        raise ValueError('Unexpected or overlapping allocation')
    if len(development) != 12 or len(reserved) != 48:
        raise ValueError('Wrong family counts in allocation')
    by_cue = defaultdict(set)
    for row in rows:
        if row['prompt_group_id'] in reserved:
            by_cue[row['cue']].add(row['prompt_group_id'])
    if dict(by_cue) != {cue: set(groups) for cue, groups in spec['reserved_families'].items()}:
        raise ValueError('Mismatched reserved cue families')
    selected = [row for row in rows if row['prompt_group_id'] in reserved]
    if len(selected) != 80:
        raise ValueError('Expected 80 reserved pair-contexts')
    return selected


def reviewed_reserve(rows, reference):
    original = indexed(reference, 'pair_id')
    reviewed = indexed(rows, 'pair_id')
    if reviewed.keys() != original.keys():
        raise ValueError('Reviewed reserve changes the reserved case allocation')
    siblings = {}
    for item_id, row in reviewed.items():
        answers = ('original', 'edited')
        stable = lambda value: {k: v for k, v in value.items() if k not in answers}
        if stable(row) != stable(original[item_id]):
            raise ValueError('Content review may change answers, not context or family')
        pair = tuple(row.get(k) for k in answers)
        if not all(isinstance(s, str) and s.strip() for s in pair) or pair[0] == pair[1]:
            raise ValueError('Expected two distinct reviewed answers')
        if siblings.setdefault(row['prompt_group_id'], pair) != pair:
            raise ValueError('Sibling contexts must retain identical candidates')
    return [reviewed[key] for key in original]


def cohort_for(path):
    if canonical_hash(path) == DEVELOPMENT_SHA256:
        return 'development'
    reviewed_reserve(read_jsonl(path), select(CORPUS, ALLOCATION))
    return 'held_out'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, default=Path('data/wording_pairs_v1.jsonl'))
    p.add_argument('--split', type=Path, default=Path('data/development_split_v1.json'))
    p.add_argument('--protocol', type=Path, default=Path('rubric/oa_protocol.json'))
    p.add_argument('--reviewed', type=Path, help='Content-reviewed answers for the same reserved contexts')
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    rows = select(args.source, args.split)
    if args.reviewed:
        rows = reviewed_reserve(read_jsonl(args.reviewed), rows)
    args.out.mkdir(parents=True, exist_ok=False)
    subset = args.out / 'reserved_pairs.jsonl'
    write_jsonl(subset, rows)
    prepare(subset, args.protocol, args.out / 'study', SEED, separate_families=True)
    write_json(args.out / 'cohort.json', {
        'status': 'candidate reserve; approval required before live scoring',
        'families': 48, 'cases': len(rows), 'candidate_trials': 2 * len(rows),
        'allocation_sha256': digest(args.split.read_bytes()),
        'source_sha256': digest(args.source.read_bytes()),
        'subset_sha256': digest(subset.read_bytes()), 'seed': SEED,
    })
    print('Prepared 48 reserved families and 80 pair-contexts. Share only the approved blinded packet.')


if __name__ == '__main__':
    main()
