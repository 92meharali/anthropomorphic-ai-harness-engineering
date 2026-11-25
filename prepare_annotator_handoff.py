"""Validate the frozen Task 5 study and export only blinded annotator materials."""
import argparse
import csv
import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

APPROVED_SHA256 = 'e7a131c007c97e1de003f08a61f3744dca9f59c2c92ff4e1bc406c3e382faaa3'
SEED = 20261123
FIELDS = ('review_id', 'pair_sha256', 'preference', 'cue_needs_correction', 'content_preserved')
FROZEN = ('oa_inputs.jsonl', 'review_packet.jsonl', 'pair_key.jsonl', 'protocol.json')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def index(rows, field):
    result = {r[field]: r for r in rows}
    require(len(result) == len(rows), f'Duplicate {field}')
    return result


def validate(study, source, split):
    raw = source.read_bytes()
    require(sha(raw) == APPROVED_SHA256, 'Approved dataset hash mismatch')
    pairs = index(jsonl(source), 'pair_id')
    allocation = json.loads(split.read_text(encoding='utf-8'))
    require(set(pairs) == set(allocation['development_pair_ids']), 'Task 3 pair IDs mismatch')
    require(len(pairs) == 20, 'Expected 20 pairs')
    require(Counter(p['cue'] for p in pairs.values()) == {'memory': 8, 'availability': 4, 'warmth': 8}, 'Unexpected cue counts')
    groups = defaultdict(list)
    for p in pairs.values():
        groups[p['prompt_group_id']].append(p)
    require(len(groups) == 12, 'Expected 12 families')
    for group, members in groups.items():
        expected = 1 if members[0]['cue'] == 'availability' else 2
        require(len(members) == expected, f'Unexpected context count: {group}')
        require(len({(p['original'], p['edited']) for p in members}) == 1, f'Inconsistent sibling wording: {group}')
    manifest = json.loads((study / 'manifest.json').read_text(encoding='utf-8'))
    require(manifest['source_sha256'] == APPROVED_SHA256, 'Manifest source mismatch')
    require(manifest['pairs'] == 20 and manifest['seed'] == SEED, 'Unexpected study size or seed')
    for name in FROZEN:
        require(sha((study / name).read_bytes()) == manifest['sha256'][name], f'Frozen file changed: {name}')
    packet = jsonl(study / 'review_packet.jsonl')
    key = index(jsonl(study / 'pair_key.jsonl'), 'review_id')
    inputs = index(jsonl(study / 'oa_inputs.jsonl'), 'item_id')
    require(len(packet) == 20 and len(key) == 20 and len(inputs) == 40, 'Unexpected packet, key or candidate count')
    require(set(index(packet, 'review_id')) == set(key), 'Packet/key IDs mismatch')
    require({k['pair_id'] for k in key.values()} == set(pairs), 'Key does not cover all approved pairs')
    rng = random.Random(SEED)
    expected_order = list(pairs)
    rng.shuffle(expected_order)
    positions = Counter()
    for n, row in enumerate(packet, 1):
        require(set(row) == {'review_id', 'prompt', 'A', 'B', 'pair_sha256'}, 'Unexpected reviewer-facing metadata')
        rid = row['review_id']
        require(rid == f'W{n:04d}', 'Unexpected neutral review ID')
        expected_hash = sha(json.dumps({k: v for k, v in row.items() if k != 'pair_sha256'}, sort_keys=True, ensure_ascii=False).encode('utf-8'))
        require(row['pair_sha256'] == expected_hash, f'Pair hash mismatch: {rid}')
        mapping = key[rid]
        require(mapping['pair_id'] == expected_order[n - 1], f'Unexpected seeded case order: {rid}')
        expected_versions = ['original', 'edited']
        rng.shuffle(expected_versions)
        require([mapping['A'], mapping['B']] == expected_versions, f'Unexpected seeded A/B order: {rid}')
        pair = pairs[mapping['pair_id']]
        require({mapping['A'], mapping['B']} == {'original', 'edited'}, f'Invalid key: {rid}')
        require(mapping['prompt_group_id'] == pair['prompt_group_id'] and mapping['cue'] == pair['cue'], f'Key metadata mismatch: {rid}')
        require(row['prompt'] == pair['prompt'], f'Prompt mismatch: {rid}')
        for pos in ('A', 'B'):
            require(row[pos] == pair[mapping[pos]], f'Candidate mismatch: {rid}-{pos}')
            require(inputs[f'{rid}-{pos}'] == {'item_id': f'{rid}-{pos}', 'prompt': row['prompt'], 'response': row[pos]}, f'OA input mismatch: {rid}-{pos}')
        positions[mapping['A']] += 1
    return packet, positions


def export(packet, guide, out):
    guide_text = guide.read_text(encoding='utf-8')
    out.mkdir(parents=True, exist_ok=False)
    (out / 'REVIEWER_GUIDE.md').write_text(guide_text, encoding='utf-8', newline='\n')
    parts = ['# Blinded chatbot answer pairs\n', 'Read REVIEWER_GUIDE.md before starting. Record one judgment per case in ballot.csv. Do not change the IDs or hashes. In the CSV, use true, false, or null for content_preserved.\n']
    for r in packet:
        parts.extend([f"## {r['review_id']}\n", '**Conversation**\n\n' + r['prompt'] + '\n', '**Answer A**\n\n' + r['A'] + '\n', '**Answer B**\n\n' + r['B'] + '\n', '---\n'])
    (out / 'review_packet.md').write_text('\n'.join(parts), encoding='utf-8', newline='\n')
    with (out / 'ballot.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for r in packet:
            writer.writerow({k: r[k] for k in FIELDS[:2]})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--study', type=Path, default=Path('private/task5-study-v1'))
    p.add_argument('--source', type=Path, default=Path('data/development_reviewed.jsonl'))
    p.add_argument('--split', type=Path, default=Path('data/development_split_v1.json'))
    p.add_argument('--guide', type=Path, default=Path('data/REVIEWER_GUIDE.md'))
    p.add_argument('--out', type=Path, default=Path('private/task5-annotator-handoff'))
    args = p.parse_args()
    try:
        packet, positions = validate(args.study, args.source, args.split)
        export(packet, args.guide, args.out)
    except (OSError, ValueError, KeyError, TypeError) as e:
        p.error(str(e))
    print('PASS: approved SHA-256, 12 families, 20 pairs, 40 candidate inputs, frozen file hashes, A/B mapping, pair hashes and blinded fields.')
    print(f'Coordinator only: A contains original {positions["original"]} times; edited {positions["edited"]} times.')
    print(f'Annotator handoff saved to {args.out}. Give each annotator a separate copy of the three files.')


if __name__ == '__main__':
    main()
