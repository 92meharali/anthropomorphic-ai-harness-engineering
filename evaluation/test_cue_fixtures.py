"""Replay synthetic study fixtures with scripted detector and guard outputs."""
from pathlib import Path
import unittest

from .data import read_jsonl
from .cue_routing import route_pair
from .test_cue_routing import frozen, provider


class CueFixtureTests(unittest.TestCase):
    def test_example_routes(self):
        path = Path(__file__).resolve().parents[1] / 'examples/cue_regressions.jsonl'
        for case in read_jsonl(path):
            prior, current = case['prior'], case['prompt']
            record = {
                'current_user_message': current, 'original': case['original'], 'edited': case['alternate'],
                'visible_history': [{'role': 'user', 'turn_id': 'u1', 'content': prior}] if prior else [],
                'prompt': f'Previous user message: {prior}\nCurrent user message: {current}' if prior else current,
            }
            item = {'cue_type': case['cue'], 'span': case['span'], 'occurrence': 0,
                    'implied_claim': case['span'], 'reason': 'Scripted fixture',
                    'evidence_status': case['assessment'], 'evidence': case['evidence']}
            for orientation in ('A', 'B'):
                with self.subTest(case=case['id'], original=orientation):
                    import json
                    def detect(body):
                        candidate = json.loads(body['input'][0]['content'])['candidate_response']
                        return provider({'status': 'ok', 'reason': 'Scripted fixture',
                                         'cues': [item] if candidate == record['original'] else []})
                    def guard(_body):
                        return provider({'preference': 'tie', 'cue_needs_correction': orientation,
                                         'content_preserved': case['preserved']})
                    trace = route_pair(record, frozen(record, orientation),
                                       detector_model='fixture', pair_model='fixture', detect=detect,
                                       judge_pair=guard, withhold_history=case.get('masked', False))
                    self.assertEqual(trace['cue_decision']['action'], case['action'])
