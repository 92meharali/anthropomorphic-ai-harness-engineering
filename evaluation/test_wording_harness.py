"""Regression checks for reviewer blinding and matched-pair score joins."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from .data import digest, read_jsonl, write_json, write_jsonl
from .run import plan
from .wording_harness import MODEL, analyze, prepare


class WordingHarnessTest(unittest.TestCase):
    def test_blinded_packet_and_comparison(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            protocol = root / 'protocol.json'
            write_json(protocol, {
                'common': 'Judge OA.', 'abstention': 'Insufficient context.',
                'dimensions': {'OA': {'rubric': 'Rate from 1 to 5.'}},
            })
            pair = {'pair_id': 'source-1', 'prompt_group_id': 'group-1',
                    'cue': 'availability', 'prompt': 'Could you explain the first step?',
                    'original': 'Check the worked example.',
                    'edited': 'I will always be here. Check the worked example.'}
            source = root / 'pairs.jsonl'
            study = root / 'study'
            write_jsonl(source, [pair])
            prepare(source, protocol, study, 13)
            packet = read_jsonl(study / 'review_packet.jsonl')[0]
            self.assertEqual(set(packet), {'review_id', 'prompt', 'A', 'B', 'pair_sha256'})
            original = 'A' if packet['A'] == pair['original'] else 'B'
            edited = 'B' if original == 'A' else 'A'
            paths = [root / f'reviewer-{number}.jsonl' for number in range(3)]
            for path, choice in zip(paths, (original, original, 'cannot_judge')):
                write_jsonl(path, [{'review_id': packet['review_id'], 'pair_sha256': packet['pair_sha256'],
                                    'preference': choice, 'cue_needs_correction': edited,
                                    'content_preserved': True}])
            inputs = read_jsonl(study / 'oa_inputs.jsonl')
            jobs = plan(inputs, json.loads(protocol.read_text()), ('openai',), {'openai': MODEL})
            oa_path, humt_path = root / 'oa.jsonl', root / 'humt.jsonl'
            write_jsonl(oa_path, [{**job, 'status': 'ok', 'rating': 4} for job in jobs])
            humt_scores = [{'item_id': row['item_id'], 'response_sha256': digest(row['response']),
                            'humt': 0.1 if row['response'] == pair['original'] else 0.9}
                           for row in inputs]
            write_jsonl(humt_path, humt_scores)
            result = analyze(study, oa_path, humt_path, paths)
            self.assertEqual(result['all_pairs']['agreement_counts']['only_humt_correct'], 1)
            self.assertEqual(result['pairs'][0]['oa'], 'tie')
            self.assertEqual(result['pairs'][0]['human'], original)

            write_jsonl(humt_path, humt_scores[:1])
            self.assertEqual(analyze(study, oa_path, humt_path, paths)['all_pairs']['common_comparable_pairs'], 0)
            humt_scores[0]['response_sha256'] = 'wrong response'
            write_jsonl(humt_path, humt_scores)
            with self.assertRaisesRegex(ValueError, 'HumT response hash mismatch'):
                analyze(study, oa_path, humt_path, paths)
            (study / 'review_packet.jsonl').write_text('{}\n')
            with self.assertRaisesRegex(ValueError, 'Frozen file changed'):
                analyze(study, oa_path, humt_path, paths)
