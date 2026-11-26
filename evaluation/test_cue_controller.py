"""Offline controller contract tests, not the Task 4 regression dataset."""
import copy
import json
import unittest
from . import cue_controller as c
from . import cue_output as o

CAPS = dict(visible_history_complete=True, can_access_prior_sessions=False,
            can_contact_or_check_in_proactively=False, can_guarantee_future_availability=False)
RECORD = {'current_user_message': 'What should I do next?', 'visible_history': [
    {'turn_id': 'u1', 'role': 'user', 'content': 'Making a list helps.'}],
    'cue': 'SECRET', 'context_condition': 'SECRET', 'human_rating': 'SECRET'}
SPAN = 'You said earlier that making a list helps.'
ORIGINAL = SPAN + ' Write a list.'
ALTERNATE = 'Write a list.'


def raw(result):
    return {'status': 'completed', 'output': [{'type': 'message', 'content': [
        {'type': 'output_text', 'text': json.dumps(result)}]}]}


def answer(status='supported', evidence=None, span=SPAN, occurrence=0, cue_type='memory'):
    if evidence is None:
        evidence = [{'source': 'history', 'reference': 'u1', 'quote': 'Making a list helps.'}]
    return {'status': 'ok', 'reason': 'Test assessment.', 'cues': [{
        'cue_type': cue_type, 'span': span, 'occurrence': occurrence,
        'implied_claim': 'Claim under test.', 'evidence_status': status,
        'evidence': evidence, 'reason': 'Test evidence judgment.'}]}


def absence():
    return answer('unsupported', [{'source': 'capability', 'reference': 'visible_history_complete', 'quote': None}])


def empty():
    return {'status': 'ok', 'reason': 'No target cue.', 'cues': []}


def passed():
    return {**{key: 'pass' for key in c.VERIFIER_SCHEMA['required'][:-1]}, 'reason': 'Test verification.'}


class ControllerTests(unittest.TestCase):
    def run_route(self, results, verification=None, oa=None, **kwargs):
        calls = []
        iterator = iter(results)
        def detect(req):
            calls.append(('detect', json.loads(req['input'][0]['content'])))
            result = next(iterator)
            if isinstance(result, Exception): raise result
            return raw(result) if 'cues' in result else result
        def verify(req):
            calls.append(('verify', json.loads(req['input'][0]['content'])))
            if isinstance(verification, Exception): raise verification
            return raw(verification if verification is not None else passed())
        def evaluate(state):
            calls.append(('oa', state))
            if isinstance(oa, Exception): raise oa
            return oa
        trace = c.route(kwargs.pop('record', RECORD), kwargs.pop('original', ORIGINAL),
                        kwargs.pop('alternate', ALTERNATE), CAPS, model='test-model',
                        detect=detect, verify=verify, evaluate_oa=evaluate if oa is not None else None,
                        **kwargs)
        return trace, calls

    def test_exact_occurrence_and_unicode_offsets(self):
        state = o.state(RECORD, '🙂aaaa', CAPS)
        report = c.validate_evidence(state, answer(span='aa', occurrence=2))
        self.assertTrue(report['valid'])
        self.assertEqual(report['cues'][0]['offsets'], [3, 5])
        self.assertFalse(c.validate_evidence(state, answer(span='aa', occurrence=3))['valid'])
        self.assertFalse(c.validate_evidence(state, answer(span='AA'))['valid'])

    def test_invalid_evidence_references_hold(self):
        for ev in [{'source': 'history', 'reference': 'u9', 'quote': 'Making a list helps.'},
                   {'source': 'history', 'reference': 'u1', 'quote': 'fabricated'},
                   {'source': 'current_user', 'reference': 'u1', 'quote': 'What should I do next?'},
                   {'source': 'current_user', 'reference': o.CURRENT_USER_REF, 'quote': 'fabricated'},
                   {'source': 'capability', 'reference': 'invented', 'quote': None},
                   {'source': 'role', 'reference': 'invented', 'quote': None}]:
            with self.subTest(ev=ev):
                trace, calls = self.run_route([answer(evidence=[ev])], oa={'status': 'ok', 'rating': 5})
                self.assertEqual(trace['cue_decision']['action'], 'hold')
                self.assertEqual(trace['original_detection']['status'], 'invalid_evidence')
                self.assertEqual(len(calls), 1)
                self.assertEqual(trace['oa']['status'], 'not_run')

    def test_resolve_trusted_values_and_current_user(self):
        state = o.state(RECORD, ORIGINAL, CAPS)
        result = answer('unsupported', [{'source': 'capability', 'reference': 'can_guarantee_future_availability', 'quote': None},
                            {'source': 'role', 'reference': 'role.no_genuine_personal_relationship', 'quote': None},
                            {'source': 'current_user', 'reference': o.CURRENT_USER_REF, 'quote': 'What should I do next?'}], cue_type='availability')
        report = c.validate_evidence(state, result)
        self.assertTrue(report['valid'])
        self.assertIs(report['cues'][0]['evidence'][0]['trusted_value'], False)
        self.assertEqual(report['cues'][0]['evidence'][1]['trusted_value'], o.ROLE_RULES['role.no_genuine_personal_relationship'])
        self.assertEqual(report['cues'][0]['evidence'][2]['role'], 'user')

    def test_keep_and_oa_pass_without_alternate(self):
        for result in (empty(), answer()):
            trace, calls = self.run_route([result], oa={'status': 'ok', 'rating': 4})
            self.assertEqual(trace['cue_decision']['action'], 'keep')
            self.assertEqual(trace['final_selected'], 'original')
            self.assertEqual([k for k, _ in calls], ['detect', 'oa'])

    def test_verified_edit_and_separate_oa(self):
        record = dict(RECORD, visible_history=[])
        trace, calls = self.run_route([absence(), empty()], record=record, oa={'status': 'ok', 'rating': 5})
        self.assertEqual(trace['cue_decision']['action'], 'edit')
        self.assertEqual(trace['final_selected'], 'alternate')
        self.assertEqual([k for k, _ in calls], ['detect', 'detect', 'verify', 'oa'])
        self.assertEqual(calls[-1][1]['candidate_response'], ALTERNATE)
        self.assertNotIn('SECRET', json.dumps(calls))
        self.assertEqual({k: v for k, v in calls[0][1].items() if k != 'candidate_response'},
                         {k: v for k, v in calls[1][1].items() if k != 'candidate_response'})
        self.assertTrue(trace['text_changes'])
        self.assertEqual(trace['verification']['result']['content_preserved'], 'pass')

    def test_unresolved_precedence_and_masked_reference(self):
        result = absence(); result['cues'] += answer('unclear', [])['cues']
        trace, calls = self.run_route([result])
        self.assertEqual(trace['cue_decision']['reason'], 'original_unresolved_cue')
        self.assertEqual(len(calls), 1)
        for result in (answer(), absence()):
            trace, calls = self.run_route([result], withhold_history=True)
            self.assertEqual(trace['cue_decision']['action'], 'hold')
            self.assertEqual(trace['original_detection']['status'], 'invalid_evidence')
            self.assertEqual(calls[0][1]['visible_history'], [])
            self.assertFalse(calls[0][1]['system_capabilities']['visible_history_complete'])
        trace, _ = self.run_route([answer('unclear', [])], withhold_history=True)
        self.assertEqual(trace['cue_decision']['reason'], 'original_unresolved_cue')

    def test_unsupported_or_unresolved_alternate_holds(self):
        for result in (answer('unsupported', [{'source':'capability','reference':'visible_history_complete','quote':None}], span=ALTERNATE),
                       answer('unclear', [], span=ALTERNATE)):
            trace, calls = self.run_route([absence(), result])
            self.assertEqual(trace['cue_decision']['action'], 'hold')
            self.assertEqual(len(calls), 2)

    def test_alternate_checks_all_required(self):
        for field in c.VERIFIER_SCHEMA['required'][:-1]:
            for status in ('fail', 'unclear'):
                result = passed(); result[field] = status
                trace, calls = self.run_route([absence(), empty()], verification=result, oa={'status':'ok','rating':5})
                self.assertEqual(trace['cue_decision']['action'], 'hold')
                self.assertIsNone(trace['final_selected'])
                self.assertEqual(len(calls), 3)
        for alternate in ('', ORIGINAL, None):
            trace, calls = self.run_route([absence()], alternate=alternate)
            self.assertEqual(trace['cue_decision']['action'], 'hold')
            self.assertEqual(len(calls), 1)

    def test_errors_and_abstention_are_not_keep(self):
        for result in (TimeoutError('secret'), {'status':'failed','output':[]},
                       {'status':'completed','output':[]}, {'status':'cannot_judge','reason':'Unknown','cues':[]}):
            trace, calls = self.run_route([result])
            self.assertEqual(trace['cue_decision']['action'], 'hold')
            self.assertEqual(len(calls), 1)
        trace, _ = self.run_route([absence(), empty()], verification=RuntimeError('secret'))
        self.assertEqual(trace['cue_decision']['reason'], 'alternate_verification_error')
        self.assertNotIn('secret', json.dumps(trace))

    def test_oa_failure_does_not_change_cue_decision(self):
        for oa, status in [({'status':'ok','rating':3}, 'requires_revision'),
                           ({'status':'cannot_judge','rating':None}, 'hold'),
                           ({'status':'ok','rating':True}, 'hold'), (TimeoutError(), 'hold'), (None, 'not_run')]:
            trace, _ = self.run_route([absence(), empty()], oa=oa)
            self.assertEqual(trace['cue_decision']['action'], 'edit')
            self.assertEqual(trace['oa']['status'], status)
            self.assertIsNone(trace['final_selected'])


if __name__ == '__main__':
    unittest.main()
