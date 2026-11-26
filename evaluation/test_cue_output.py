"""Offline tests for Task 2's input and output contracts (synthetic fixtures)."""
import copy
import json
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from evaluation import cue_output as cue

CAPS = dict(visible_history_complete=True, can_access_prior_sessions=False,
            can_contact_or_check_in_proactively=False, can_guarantee_future_availability=False)
RECORD = {'current_user_message': 'How can I start?', 'visible_history': [
    {'turn_id': 'u1', 'role': 'user', 'content': 'Timers help me.'}],
    'pair_id': 'SECRET_ID', 'cue': 'SECRET_CUE', 'context_condition': 'SECRET_CONDITION',
    'original': 'SECRET_ORIGINAL', 'edited': 'SECRET_EDIT', 'human_votes': ['SECRET_VOTE'],
    'prompt': 'SECRET_RENDERED_PROMPT', 'system_capabilities': {'can_access_prior_sessions': True}}
DRAFT = 'You said timers help you. Try five minutes.'


def supported():
    return {'status': 'ok', 'reason': 'A grounded reference.', 'cues': [
        {'cue_type': 'memory', 'span': 'You said timers help you.', 'occurrence': 0,
         'implied_claim': 'The user previously said timers help.', 'evidence_status': 'supported',
         'evidence': [{'source': 'history', 'reference': 'u1', 'quote': 'Timers help me.'}],
         'reason': 'The prior user turn supports the paraphrase.'}]}


def response(value):
    return {'status': 'completed', 'output': [{'type': 'message', 'content': [
        {'type': 'output_text', 'text': json.dumps(value)}]}]}


class CueOutputTests(unittest.TestCase):
    def test_trusted_manifest(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'manifest.json'
            path.write_text(json.dumps({'system_capabilities': CAPS}), encoding='utf-8')
            self.assertEqual(cue.load_capabilities(path), CAPS)
            path.write_text(json.dumps({'system_capabilities': {**CAPS, 'extra': True}}), encoding='utf-8')
            with self.assertRaises(ValueError):
                cue.load_capabilities(path)
        with self.assertRaises(ValueError):
            cue.state(RECORD, DRAFT, {**CAPS, 'visible_history_complete': 1})

    def test_request_allowlist_and_shared_guide(self):
        request = cue.request_body('fixture-model', RECORD, DRAFT, CAPS)
        state = json.loads(request['input'][0]['content'])
        self.assertEqual(set(state), {'current_user_message', 'visible_history', 'candidate_response',
                                     'system_capabilities', 'trusted_role_rules'})
        self.assertEqual(state['candidate_response'], DRAFT)
        self.assertEqual(state['system_capabilities'], CAPS)
        self.assertIn(cue.load_guide(), request['instructions'])
        self.assertIn(cue.RUBRIC_PATH.read_text(encoding='utf-8'), request['instructions'])
        self.assertNotIn('SECRET_', json.dumps(request))
        self.assertFalse(request['store'])
        self.assertTrue(request['text']['format']['strict'])
        self.assertEqual(len(cue.request_sha256(request)), 64)

    def test_masked_history_is_not_complete(self):
        full = cue.state(RECORD, DRAFT, CAPS)
        masked = cue.state(RECORD, DRAFT, CAPS, withhold_history=True)
        self.assertEqual(masked['visible_history'], [])
        self.assertNotIn('Timers help me.', json.dumps(masked))
        self.assertFalse(masked['system_capabilities']['visible_history_complete'])
        self.assertTrue(full['system_capabilities']['visible_history_complete'])
        self.assertTrue(CAPS['visible_history_complete'])
        self.assertEqual(masked['candidate_response'], full['candidate_response'])
        self.assertEqual(masked['current_user_message'], full['current_user_message'])

    def test_invalid_history(self):
        for history in (None, [{'turn_id': 'u1', 'role': 'system', 'content': 'x'}],
                        RECORD['visible_history'] * 2,
                        [{'turn_id': cue.CURRENT_USER_REF, 'role': 'user', 'content': 'x'}]):
            with self.subTest(history=history), self.assertRaises(ValueError):
                cue.state({**RECORD, 'visible_history': history}, DRAFT, CAPS)

    def test_valid_supported_unsupported_and_unclear(self):
        value = supported()
        self.assertEqual(cue.parse_structured(value), value)
        value['cues'][0].update(evidence_status='unsupported', evidence=[
            {'source': 'capability', 'reference': 'visible_history_complete', 'quote': None}])
        self.assertEqual(cue.parse_structured(value), value)
        value['cues'][0].update(evidence_status='unclear', evidence=[])
        self.assertEqual(cue.parse_structured(value), value)

    def test_no_cue_and_abstention_are_distinct(self):
        empty = {'status': 'ok', 'reason': 'No target cue.', 'cues': []}
        abstention = {'status': 'cannot_judge', 'reason': 'Unresolved assessment.', 'cues': []}
        self.assertNotEqual(cue.parse_structured(empty), cue.parse_structured(abstention))
        with self.assertRaises(ValueError):
            cue.parse_structured({**supported(), 'status': 'cannot_judge'})

    def test_reject_wrong_fields_types_and_categories(self):
        for change in ({'occurrence': True}, {'occurrence': -1}, {'span': ' '},
                       {'cue_type': 'other'}, {'evidence_status': 'maybe'}, {'evidence': []},
                       {'extra': 'leak'}):
            value = supported()
            value['cues'][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                cue.parse_structured(value)
        with self.assertRaises(ValueError):
            cue.parse_structured({**supported(), 'action': 'keep'})

    def test_evidence_quote_contract(self):
        for evidence in ({'source': 'history', 'reference': 'u1', 'quote': None},
                         {'source': 'capability', 'reference': 'key', 'quote': 'invented'},
                         {'source': 'unknown', 'reference': 'x', 'quote': None}):
            value = supported()
            value['cues'][0]['evidence'] = [evidence]
            with self.subTest(evidence=evidence), self.assertRaises(ValueError):
                cue.parse_structured(value)
        # Reference existence and semantic accuracy are intentionally deferred to Task 3.
        value = supported()
        value['cues'][0]['evidence'][0]['reference'] = 'nonexistent'
        self.assertEqual(cue.parse_structured(value), value)

    def test_provider_failures_and_strict_json(self):
        self.assertEqual(cue.parse_openai(response(supported())), supported())
        for raw in ({'status': 'incomplete'}, {'status': 'failed'},
                    {'status': 'completed', 'output': []},
                    {'status': 'completed', 'output': None},
                    {'status': 'completed', 'output': [None]},
                    {'status': 'completed', 'output': [{'type': 'message', 'content': None}]},
                    {'status': 'completed', 'output': [{'type': 'message', 'content': [None]}]},
                    {'status': 'completed', 'output': [{'type': 'message', 'content': [
                        {'type': 'refusal', 'refusal': 'declined'}]}]}):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                cue.parse_openai(raw)
        for bad in ('{"status":"ok","status":"ok"}', '{"value":NaN}'):
            with self.assertRaises(ValueError):
                cue.loads(bad)

    def test_schema_matches_parser_fields(self):
        schema = json.loads(cue.SCHEMA_PATH.read_text(encoding='utf-8'))
        value = supported()
        self.assertEqual(set(schema['required']), set(value))
        cs = schema['properties']['cues']['items']
        self.assertEqual(set(cs['required']), set(value['cues'][0]))
        self.assertEqual(set(cs['properties']['evidence']['items']['required']),
                         set(value['cues'][0]['evidence'][0]))


if __name__ == '__main__':
    unittest.main()
