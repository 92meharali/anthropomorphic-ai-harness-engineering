"""Offline contract tests. Full policy regression fixtures belong to Task 4."""
import copy
import json
import unittest
from . import cue_output as c

CAPS = dict(visible_history_complete=True, can_access_prior_sessions=False,
            can_contact_or_check_in_proactively=False, can_guarantee_future_availability=False)
RECORD = {'current_user_message': 'What should I do next?', 'visible_history': [
    {'turn_id': 'u1', 'role': 'user', 'content': 'Making a list helps.'}],
    'cue': 'memory', 'context_condition': 'supported', 'original': 'SECRET ORIGINAL',
    'edited': 'SECRET EDITED', 'prompt': 'SECRET FLATTENED HISTORY', 'pair_id': 'M001',
    'preference': 'A', 'human_score': 5}
SPAN = 'You said earlier that making a list helps.'


def answer():
    return {'status': 'ok', 'reason': 'A prior disclosure is claimed.', 'cues': [{
        'cue_type': 'memory', 'span': SPAN, 'occurrence': 0,
        'implied_claim': 'User previously said making a list helps.', 'evidence_status': 'supported',
        'evidence': [{'source': 'history', 'reference': 'u1', 'quote': 'Making a list helps.'}],
        'reason': 'The displayed user turn supports the claim.'}]}


def raw(value):
    return {'status': 'completed', 'output': [{'type': 'message', 'content': [
        {'type': 'output_text', 'text': json.dumps(value)}]}]}


class CueOutputTests(unittest.TestCase):
    def test_request_allowlist_and_schema(self):
        req = c.request_body('test-model', RECORD, SPAN, CAPS)
        payload = json.loads(req['input'][0]['content'])
        self.assertEqual(set(payload), {'current_user_message', 'visible_history',
                         'candidate_response', 'system_capabilities', 'trusted_role_rules'})
        self.assertEqual(payload['candidate_response'], SPAN)
        self.assertNotIn('SECRET', req['input'][0]['content'])
        self.assertIn('role.no_genuine_personal_relationship', payload['trusted_role_rules'])
        self.assertTrue(req['text']['format']['strict'])
        self.assertFalse(req['store'])

    def test_ablation_does_not_leak_history(self):
        before = copy.deepcopy(CAPS)
        full = c.state(RECORD, SPAN, CAPS)
        masked = c.state(RECORD, SPAN, CAPS, withhold_history=True)
        self.assertEqual(masked['visible_history'], [])
        self.assertFalse(masked['system_capabilities']['visible_history_complete'])
        self.assertEqual(CAPS, before)
        self.assertTrue(full['system_capabilities']['visible_history_complete'])
        self.assertEqual(full['current_user_message'], masked['current_user_message'])
        self.assertEqual(full['candidate_response'], masked['candidate_response'])

    def test_supported_and_absent_and_unclear_shapes(self):
        a = answer()
        self.assertEqual(c.parse_openai(raw(a)), a)
        a['cues'][0].update(evidence_status='unsupported', evidence=[{
            'source': 'capability', 'reference': 'visible_history_complete', 'quote': None}])
        self.assertEqual(c.parse_openai(raw(a)), a)
        a['cues'][0].update(evidence_status='unclear', evidence=[])
        self.assertEqual(c.parse_openai(raw(a)), a)

    def test_role_and_multiple_claims(self):
        a = answer()
        for claim, reference, source in [('Enduring friendship', 'role.no_genuine_personal_relationship', 'role'),
                ('Guaranteed future availability', 'can_guarantee_future_availability', 'capability')]:
            a['cues'].append({'cue_type': 'availability', 'span': 'I will always be your friend.',
                'occurrence': 0, 'implied_claim': claim, 'evidence_status': 'unsupported',
                'evidence': [{'source': source, 'reference': reference, 'quote': None}], 'reason': 'Conflicts.'})
        self.assertEqual(len(c.parse_structured(a)['cues']), 3)

    def test_empty_is_not_abstention(self):
        no_cue = {'status': 'ok', 'reason': 'Bounded assistance only.', 'cues': []}
        abstain = {'status': 'cannot_judge', 'reason': 'Unable to assess.', 'cues': []}
        self.assertEqual(c.parse_openai(raw(no_cue)), no_cue)
        self.assertEqual(c.parse_openai(raw(abstain)), abstain)
        a = answer(); a['status'] = 'cannot_judge'
        with self.assertRaises(ValueError): c.parse_structured(a)

    def test_bad_fields_and_types(self):
        for changes in ({'cue_type': 'other'}, {'occurrence': True}, {'occurrence': -1},
                        {'span': ''}, {'evidence': []}, {'action': 'keep'}, {'evidence_status': 'maybe'}):
            with self.subTest(changes=changes):
                a = answer(); a['cues'][0].update(changes)
                with self.assertRaises(ValueError): c.parse_structured(a)
        a = answer(); a['cues'][0]['evidence'][0]['quote'] = None
        with self.assertRaises(ValueError): c.parse_structured(a)
        a = answer(); a['action'] = 'edit'
        with self.assertRaises(ValueError): c.parse_structured(a)

    def test_provider_failure_not_empty_success(self):
        for status in ('incomplete', 'failed', 'cancelled'):
            result = c.parse_openai({'status': status, 'output': []})
            self.assertNotEqual(result['status'], 'ok'); self.assertIsNone(result['cues'])
        result = c.parse_openai({'status': 'completed', 'output': [{'type': 'message',
            'content': [{'type': 'refusal', 'refusal': 'No'}]}]})
        self.assertEqual(result['status'], 'refusal'); self.assertIsNone(result['cues'])
        with self.assertRaises(ValueError): c.parse_openai({'status': 'completed', 'output': []})
        r = raw(answer()); r['output'][0]['content'][0]['text'] = '{"status":"ok","status":"ok"}'
        with self.assertRaises(ValueError): c.parse_openai(r)

    def test_trust_and_input_errors(self):
        bad = dict(CAPS, visible_history_complete=1)
        with self.assertRaises(ValueError): c.state(RECORD, SPAN, bad)
        bad_record = dict(RECORD, visible_history=RECORD['visible_history'] * 2)
        with self.assertRaises(ValueError): c.state(bad_record, SPAN, CAPS)
        with self.assertRaises(ValueError): c.state({'prompt': 'legacy only'}, SPAN, CAPS)

    def test_reference_existence_is_task3(self):
        a = answer(); a['cues'][0]['evidence'][0]['reference'] = 'not-a-real-turn'
        # Structure alone is not evidence validation or permission to select an answer.
        self.assertEqual(c.parse_structured(a), a)


if __name__ == '__main__':
    unittest.main()
