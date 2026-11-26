"""Prepare the reserved wording cohort and a separated A/B packet."""
import argparse
from collections import defaultdict
import json
from pathlib import Path

from .data import digest, read_jsonl, write_json, write_jsonl
from .wording_harness import prepare

SEED = 20261126


def select(source, split):
    spec = json.loads(split.read_text())
    raw = source.read_bytes()
    if digest(raw.replace(b'\r\n', b'\n')) != spec['source_sha256']:
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


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, default=Path('data/wording_pairs_v1.jsonl'))
    p.add_argument('--split', type=Path, default=Path('data/development_split_v1.json'))
    p.add_argument('--protocol', type=Path, default=Path('rubric/oa_protocol.json'))
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    rows = select(args.source, args.split)
    args.out.mkdir(parents=True, exist_ok=False)
    subset = args.out / 'reserved_pairs.jsonl'
    write_jsonl(subset, rows)
    prepare(subset, args.protocol, args.out / 'study', SEED, separate_families=True)
    write_json(args.out / 'cohort.json', {
        'status': 'reserved cohort prepared for independent content review',
        'families': 48, 'cases': len(rows), 'candidate_trials': 2 * len(rows),
        'allocation_sha256': digest(args.split.read_bytes()),
        'source_sha256': digest(args.source.read_bytes()),
        'subset_sha256': digest(subset.read_bytes()), 'seed': SEED,
    })
    print('Prepared 48 reserved families and 80 pair-contexts. Share only the approved blinded packet.')


if __name__ == '__main__':
    main()
