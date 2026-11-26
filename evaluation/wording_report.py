"""Aggregate frozen fixed-pair decisions against blinded human ballots."""
import argparse
from collections import Counter, defaultdict
from itertools import combinations
import json
import math
from pathlib import Path
import random

from . import humt as humt_scorer, pair_judge
from .data import digest, read_jsonl, write_json
from .run_wording import verify_run
from .wording_harness import indexed, signed_choice

ARMS = ('keep_original', 'lower_humt', 'frozen_oa', 'direct_pair', 'full', 'masked')
PICKS = ('A', 'B')
JUDGMENTS = {
    'preference': {'A', 'B', 'tie'},
    'cue_needs_correction': {'A', 'B', 'both', 'neither'},
    'content_preserved': {True, False},
}


def fraction(n, d):
    return n / d if d else None


def reference(field, votes):
    choices = JUDGMENTS[field]
    return next((v for v, n in Counter(votes).items() if n >= 2 and v in choices), None)


def family_interval(cases, draws=10000):
    families = defaultdict(lambda: [0, 0])
    for case in cases:
        ref = case['human']['preference']
        if ref is not None:
            agg = families[case['group']]
            agg[0] += int(case['choices']['full'] == ref) - int(case['choices']['frozen_oa'] == ref)
            agg[1] += 1
    blocks = list(families.values())
    if not blocks:
        return {'families': 0, 'difference': None, 'interval_95': None}
    rng = random.Random(20261126)
    distribution = []
    for _ in range(draws):
        sample = rng.choices(blocks, k=len(blocks))
        distribution.append(sum(x[0] for x in sample) / sum(x[1] for x in sample))
    distribution.sort()
    return {'families': len(blocks), 'draws': draws, 'seed': 20261126,
            'difference': sum(x[0] for x in blocks) / sum(x[1] for x in blocks),
            'interval_95': [distribution[int((draws-1)*.025)], distribution[int((draws-1)*.975)]]}


def metrics(cases, arm):
    totals = Counter()
    final = Counter()
    for case in cases:
        pick = case['choices'][arm]
        orig = case['original']
        ref = case['human']['preference']
        if ref is not None:
            totals['eligible'] += 1
            if pick in ('A', 'B', 'tie'):
                totals['comparable'] += 1
                totals['matches'] += pick == ref
        if pick in PICKS:
            totals['selected'] += 1
            edits = pick != orig
            totals['edits'] += edits
            correction = case['human']['cue_needs_correction']
            if correction is not None:
                totals['selected_with_correction_reference'] += 1
                totals['selected_cue_needing_correction'] += correction in (pick, 'both')
                if correction not in (orig, 'both'):
                    totals['selected_acceptable_original_cases'] += 1
                    totals['edits_to_acceptable_originals'] += edits
            if edits and case['human']['content_preserved'] is not None:
                totals['edits_with_preservation_reference'] += 1
                totals['edits_preserving_content'] += case['human']['content_preserved'] is True
            if case['cue'] == 'warmth':
                totals['warmth_cases_selected'] += 1
                totals['warmth_retained'] += pick == orig
                if ref == orig:
                    totals['warmth_preferred_cases_selected'] += 1
                    totals['preferred_warmth_retained'] += pick == orig
            score = case['oa'][pick]
            final['oa_pass' if score is not None and score >= 4 else 'oa_review'] += 1
        else:
            final[pick] += 1
    return {'cases': len(cases), 'counts': dict(totals),
            'choices': dict(Counter(c['choices'][arm] for c in cases)),
            'final': dict(final),
            'agreement_all_eligible': fraction(totals['matches'], totals['eligible']),
            'agreement_comparable': fraction(totals['matches'], totals['comparable']),
            'coverage_among_eligible': fraction(totals['comparable'], totals['eligible']),
            'hold_rate': fraction(final['hold'] + final['unresolved'], len(cases))}


def verified_humt(study, humt_path, expected_ids):
    manifest = json.loads((humt_path.parent / 'manifest.json').read_text())
    expected = {
        'upstream_commit': humt_scorer.UPSTREAM, 'model': humt_scorer.MODEL,
        'revision': humt_scorer.REVISION, 'character_limit': humt_scorer.CHAR_LIMIT,
        'dropout_samples_per_group': humt_scorer.SAMPLES, 'seed': humt_scorer.SEED,
        'seed_policy': 'base seed plus 32-bit scored-text digest prefix',
        'device': 'cpu', 'threads': 1,
        'input_sha256': digest((study / 'oa_inputs.jsonl').read_bytes()),
        'scorer_sha256': digest(Path(humt_scorer.__file__).read_bytes()),
        'output_sha256': digest(humt_path.read_bytes()), 'responses': len(expected_ids),
    }
    if any(manifest.get(k) != v for k, v in expected.items()):
        raise ValueError('HumT manifest does not match the pinned scorer, study or output')
    versions = manifest.get('versions', {})
    if (str(versions.get('torch', '')).split('+')[0] != '2.7.1'
            or versions.get('transformers') != '4.52.4'):
        raise ValueError('HumT dependency versions differ from the pinned environment')
    scores = indexed(read_jsonl(humt_path), 'item_id')
    if scores.keys() != expected_ids:
        raise ValueError('HumT must cover every candidate in the frozen study')
    return scores


def summarize(study, source, run, humt_path, reviewer_paths):
    manifest_path = study / 'manifest.json'
    replayed, logs = verify_run(study, source, run)
    packet = indexed(read_jsonl(study / 'review_packet.jsonl'), 'review_id')
    keys = indexed(read_jsonl(study / 'pair_key.jsonl'), 'review_id')
    results = indexed(replayed, 'review_id')
    humt = verified_humt(study, humt_path, {f'{rid}-{p}' for rid in packet for p in PICKS})
    if len({p.resolve() for p in reviewer_paths}) != 3:
        raise ValueError('Supply three separate reviewer files')
    reviewers = [indexed(read_jsonl(p), 'review_id') for p in reviewer_paths]
    if not packet or any(rows.keys() != packet.keys() for rows in [keys, results, *reviewers]):
        raise ValueError('Packet, predictions or ballot coverage mismatch')

    cases = []
    inter = {f: Counter() for f in JUDGMENTS}
    for rid, pair in packet.items():
        pair_judge.verify_pair(pair)
        output, key = results[rid], keys[rid]
        ballots = [r[rid] for r in reviewers]
        h = pair['pair_sha256']
        if any(row['pair_sha256'] != h for row in [output, *ballots]):
            raise ValueError(f'Case hash mismatch for {rid}')
        original = next(p for p in PICKS if key[p] == 'original')
        if (output['prompt_group_id'], output['cue'], output['original_position']) != (
                key['prompt_group_id'], key['cue'], original):
            raise ValueError(f'Case metadata mismatch for {rid}')
        human = {}
        for row in ballots:
            pair_judge.parse_judgments({f: row[f] for f in JUDGMENTS})
        for field, allowed in JUDGMENTS.items():
            votes = [row[field] for row in ballots]
            human[field] = reference(field, votes)
            for a, b in combinations(votes, 2):
                if a in allowed and b in allowed:
                    inter[field]['comparable'] += 1
                    inter[field]['matches'] += a == b
        values, oa = {}, {}
        for pos in PICKS:
            score = humt[f'{rid}-{pos}']
            value = score['humt']
            if score['response_sha256'] != digest(pair[pos]):
                raise ValueError(f'HumT scored different text for {rid}-{pos}')
            if type(value) not in (float, int) or not math.isfinite(value):
                raise ValueError('Invalid HumT result')
            values[pos] = value
            result = output['oa'][pos]
            rating = result['rating'] if result['status'] == 'ok' else None
            if rating is not None and (type(rating) is not int or rating not in range(1, 6)):
                raise ValueError('Invalid OA result')
            oa[pos] = rating
        choices = {**output['choices'], 'lower_humt': signed_choice(values['A'], values['B'], lower=True)}
        if set(choices) != set(ARMS) or any(v not in ('A', 'B', 'tie', 'hold', 'unresolved') for v in choices.values()):
            raise ValueError(f'Unexpected arm decisions for {rid}')
        cases.append({'group': key['prompt_group_id'], 'cue': key['cue'], 'human': human,
                      'original': original, 'oa': oa, 'choices': choices})

    usage = defaultdict(Counter)
    for row in logs:
        if row['review_id'] not in packet:
            raise ValueError('Call trace is not from the frozen packet')
        stage = row['stage'].removesuffix('_A').removesuffix('_B')
        agg = usage[stage]
        agg['requests'] += 1
        agg['latency_seconds_total'] += row['latency_seconds']
        tokens = row.get('usage') or {}
        for token in ('input_tokens', 'output_tokens'):
            if type(tokens.get(token)) is int:
                agg[token] += tokens[token]
        agg['requests_without_token_usage'] += not bool(tokens)

    return {'methods': {arm: metrics(cases, arm) for arm in ARMS},
            'by_cue': {cue: {arm: metrics([c for c in cases if c['cue'] == cue], arm) for arm in ARMS}
                       for cue in sorted({c['cue'] for c in cases})},
            'full_minus_oa_agreement': family_interval(cases),
            'reviewer_pairwise': {f: {**v, 'agreement': fraction(v['matches'], v['comparable'])}
                                  for f, v in inter.items()},
            'shared_call_usage_by_stage': {k: dict(v) for k, v in usage.items()},
            'input_sha256': {'study_manifest': digest(manifest_path.read_bytes()),
                             'run_manifest': digest((run / 'manifest.json').read_bytes()),
                             'predictions': digest((run / 'pairs.jsonl').read_bytes()),
                             'requests': digest((run / 'requests_and_results.jsonl').read_bytes()),
                             'humt_manifest': digest((humt_path.parent / 'manifest.json').read_bytes()),
                             'humt': digest(humt_path.read_bytes()),
                             'ballots': [digest(p.read_bytes()) for p in reviewer_paths]}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--humt', type=Path, required=True)
    parser.add_argument('--reviewers', type=Path, nargs=3, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = summarize(args.study, args.source, args.run, args.humt, args.reviewers)
    args.out.mkdir(parents=True, exist_ok=False)
    write_json(args.out / 'comparison.json', result)
    print(f'Saved comparison to {args.out}')


if __name__ == '__main__':
    main()
