"""Offline tests: mocked original collection, integrity, and matched requests."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import urllib.error

from . import rewrite_freeze as f


def response(text, model='mock-snapshot'):
    return {'status': 'completed', 'model': model,
            'output': [{'type': 'message', 'role': 'assistant',
                        'content': [{'type': 'output_text', 'text': text}]}]}


class FreezeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # A compact test checkout with the actual new protocol and synthetic prior.
        for path in f.DEPENDENCIES:
            dest = self.root / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            original = f.ROOT / path
            if path in (f.PROMPTS, f.PROTOCOL, 'rubric/generated_rewrite_review_v1.md',
                        'docs/GENERATED_REWRITE_FREEZE.md', 'evaluation/rewrite_freeze.py'):
                shutil.copyfile(original, dest)
            else:
                dest.write_text('test dependency', encoding='utf-8')
        self.config = f.load(self.root / f.PROTOCOL)
        (self.root / f.PRIOR_MANIFEST).write_text(json.dumps({'system_capabilities': self.config['capabilities']}))
        (self.root / f.PRIOR).write_text(json.dumps({'prompt_group_id': 'old', 'current_user_message': 'A distinct test example'})+'\n')
        self.plan = self.root / 'plan'
        self.collection = self.root / 'collection'
        self.study = self.root / 'study'
        self.calls = 0

    def prepare(self):
        return f.prepare(self.root, self.plan, 'synthetic test only')

    def mock(self, provider, request, key):
        self.assertEqual(provider, 'openai')
        self.assertNotIn('sampling_stratum', request)
        self.calls += 1
        return response('Mock original ' + str(self.calls)), 'mock-request-id'

    def collect(self, transport=None):
        self.prepare()
        return f.collect(self.root, self.plan, self.collection, 'fake-test-key', 48, transport or self.mock)

    def seal(self):
        self.collect()
        return f.freeze(self.root, self.plan, self.collection, self.study)

    def test_cohort_and_request(self):
        plan = self.prepare()
        self.assertEqual(len(plan['body']['jobs']), 48)
        self.assertEqual(self.calls, 0)
        for job in plan['body']['jobs']:
            self.assertEqual(job['request']['input'][-1]['content'], job['prompt']['current_user_message'])
            self.assertNotIn(job['prompt']['draft_id'], json.dumps(job['request']))
            self.assertEqual(job['request']['store'], False)

    def test_complete_freeze_and_verify(self):
        seal = self.seal()
        self.assertEqual(seal['manifest']['valid_drafts'], 48)
        self.assertEqual(self.calls, 48)
        self.assertEqual(f.verify(self.root, self.study), seal)
        self.assertNotIn('fake-test-key', (self.study/'attempts.jsonl').read_text())
        self.assertEqual(f.rows(self.study/'drafts.jsonl')[0]['draft'], 'Mock original 1')

    def test_tampered_draft_rejected(self):
        self.seal()
        with (self.study/'drafts.jsonl').open('a') as stream:
            stream.write('{}\n')
        with self.assertRaisesRegex(ValueError, 'original text'):
            f.verify(self.root, self.study)

    def test_changed_dependency_rejected(self):
        self.prepare()
        with (self.root / 'evaluation/cue_routing.py').open('a') as stream:
            stream.write('changed')
        with self.assertRaisesRegex(ValueError, 'changed'):
            f.collect(self.root, self.plan, self.collection, 'fake-test-key', 48, self.mock)
        self.assertEqual(self.calls, 0)

    def test_original_failure_retained(self):
        def transport(provider, body, key):
            if self.calls == 0:
                self.calls += 1
                return {'status': 'incomplete'}, 'mock-fail'
            return self.mock(provider, body, key)
        self.collect(transport)
        result = f.freeze(self.root, self.plan, self.collection, self.study)
        self.assertEqual(result['manifest']['valid_drafts'], 47)
        self.assertEqual(result['manifest']['failed_original_ids'], ['GR-M01'])
        self.assertEqual(f.verify(self.root, self.study), result)

    def test_terminal_failure_stops_and_cannot_freeze(self):
        def transport(provider, body, key):
            raise urllib.error.HTTPError('https://example.invalid', 429, 'rate limit', {}, None)
        self.assertFalse(self.collect(transport)['complete'])
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            f.freeze(self.root, self.plan, self.collection, self.study)

    def test_model_mismatch_stops_freeze(self):
        def transport(provider, body, key):
            self.calls += 1
            return response('draft', 'snapshot-1' if self.calls == 1 else 'snapshot-2'), None
        self.collect(transport)
        with self.assertRaisesRegex(ValueError, 'different original model'):
            f.freeze(self.root, self.plan, self.collection, self.study)

    def test_reused_prompt_rejected(self):
        prompt = f.rows(self.root / f.PROMPTS)[0]
        (self.root / f.PRIOR).write_text(json.dumps(prompt)+'\n')
        with self.assertRaisesRegex(ValueError, 'Duplicate or reused'):
            self.prepare()

    def test_only_validated_feedback_differs(self):
        state = {'current_user_message': 'Help', 'candidate_response': 'draft'}
        record = {'draft': 'draft'}
        cue = {'span': 'draft', 'cue_type': 'memory', 'implied_claim': 'recall',
               'evidence_status': 'unsupported', 'checked_evidence': [{'reference': 'capability'}]}
        assessment = {'status': 'ok', 'classification': 'correction', 'checked_cues': [cue]}
        kwargs = {'state_builder': lambda *args: dict(state)}
        a = f.rewrite_request(record, self.config, 'cue_specific', assessment, **kwargs)
        b = f.rewrite_request(record, self.config, 'generic', assessment, **kwargs)
        av = json.loads(a.pop('input')[0]['content']); bv = json.loads(b.pop('input')[0]['content'])
        self.assertEqual(a, b)
        feedback = av.pop('validated_cue_feedback')
        self.assertEqual(av, bv)
        self.assertEqual(feedback, [{k: cue[k] for k in self.config['flagging']['feedback_fields']}])
        with self.assertRaisesRegex(ValueError, 'Only flagged'):
            f.rewrite_request(record, self.config, 'generic', {'classification': 'unresolved'}, **kwargs)

    def test_call_budget_and_no_overwrite(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError, 'call budget'):
            f.collect(self.root, self.plan, self.collection, 'fake-test-key', 47, self.mock)
        self.assertEqual(self.calls, 0)
        with self.assertRaises(FileExistsError):
            self.prepare()


class RepositoryIntegrationTests(unittest.TestCase):
    @unittest.skipUnless(all((f.ROOT / path).is_file() for path in f.DEPENDENCIES),
                         'requires full repository checkout')
    def test_real_checkout_plan_and_harness_state(self):
        from . import cue_output, cue_routing
        plan = f.build_plan(f.ROOT, 'offline integration test only')
        config = plan['body']['config']
        self.assertEqual(len(plan['body']['jobs']), 48)
        self.assertTrue(callable(cue_routing._assessment))
        self.assertEqual(cue_output.load_capabilities(), config['capabilities'])
        record = {**plan['body']['jobs'][0]['prompt'], 'draft': 'Mock draft text'}
        detector = cue_output.request_body(config['detector_model'], record,
                                           record['draft'], config['capabilities'])
        state = json.loads(detector['input'][0]['content'])
        self.assertEqual(state['candidate_response'], record['draft'])
        self.assertNotIn('sampling_stratum', state)
        cue = {'span': 'Mock draft text', 'cue_type': 'memory', 'implied_claim': 'mock claim',
               'evidence_status': 'unsupported', 'checked_evidence': []}
        # This is a synthetic checked assessment; it is not a detector judgment.
        assessment = {'status': 'ok', 'classification': 'correction', 'checked_cues': [cue]}
        generic = f.rewrite_request(record, config, 'generic', assessment)
        specific = f.rewrite_request(record, config, 'cue_specific', assessment)
        self.assertEqual(json.loads(generic['input'][0]['content']), state)
        augmented = json.loads(specific['input'][0]['content'])
        self.assertEqual(len(augmented.pop('validated_cue_feedback')), 1)
        self.assertEqual(augmented, state)


if __name__ == '__main__':
    unittest.main()
