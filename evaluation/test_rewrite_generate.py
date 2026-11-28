"""Offline tests; provider outputs are fixtures, never study observations."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import urllib.error
from . import rewrite_freeze as f, rewrite_generate as g
from . import test_rewrite_freeze as fixtures


def state(record, draft, caps):
    return {'candidate_response': draft, 'current_user_message': record['current_user_message'],
            'visible_history': record['visible_history'], 'system_capabilities': caps}


def assess(model, record, draft, caps, withheld, detect):
    assert not withheld
    raw = detect({'model': model, 'input': state(record, draft, caps)})
    if not raw or raw.get('classification') != 'correction':
        return {'status': 'ok' if raw else 'error', 'classification': raw['classification'] if raw else 'unresolved', 'checked_cues': []}
    return {'status': 'ok', 'classification': 'correction', 'checked_cues': [
        {'span': draft, 'cue_type': 'availability', 'implied_claim': 'mock claim',
         'checked_evidence': [], 'evidence_status': 'unsupported'}]}


class GenerationTests(unittest.TestCase):
    def test_saved_assessment_does_not_call_detector(self):
        config = f.load(f.ROOT / f.PROTOCOL)
        draft = {
            'draft_id': 'W9000', 'prompt_group_id': 'test', 'draft_model': 'fixture',
            'current_user_message': 'Can you help me prepare a checklist?', 'visible_history': [],
            'draft': 'I will check in next week. Write the checklist today.',
        }
        draft['saved_assessment'] = assess(
            'fixture', draft, draft['draft'], config['capabilities'], False,
            lambda _: {'classification': 'correction'},
        )
        stages = []
        def request(stage, body):
            stages.append(stage)
            return fixtures.response(json.dumps({'response': 'Write the checklist today.'}))
        outcome = g.evaluate(draft, config, g.ARMS, request,
                             assess=lambda *_: self.fail('unexpected detector call'),
                             build_state=state)
        self.assertTrue(outcome['pair_eligible'])
        self.assertEqual(stages, list(g.ARMS))

    def setUp(self):
        self.fixture = fixtures.FreezeTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        shutil.copyfile(f.ROOT / g.SOURCE, self.root / g.SOURCE)
        self.study = self.fixture.study
        self.seal = self.fixture.seal()['freeze_sha256']
        self.out = self.root / 'run'
        self.requests = []

    def transport(self, provider, body, key):
        self.requests.append(body)
        if isinstance(body['input'], dict):
            draft = body['input']['candidate_response']
            return {'classification': 'correction' if draft in ('Mock original 1','Mock original 2') else 'acceptable', 'model': 'detector-snapshot'}, None
        payload = json.loads(body['input'][0]['content'])
        return fixtures.response(json.dumps({'response': payload['candidate_response']})), None

    def run_mock(self, transport=None, budget=144, expected=None):
        return g.run(self.root, self.study, self.out, expected or self.seal, 'fake-test-key', budget,
                     transport or self.transport, assess=assess, build_state=state)

    def verify(self):
        return g.verify(self.root, self.study, self.out, self.seal, assess=assess, build_state=state)

    def test_matched_generation_and_replay(self):
        status, summary = self.run_mock()
        self.assertEqual(status['state'], 'complete')
        self.assertEqual(summary['screened'], 48)
        self.assertEqual(summary['flagged'], 2)
        self.assertEqual(summary['eligible_pairs'], 2)
        self.assertEqual(summary['calls'], 52)
        self.assertEqual(summary['arms']['generic']['unchanged'], 2)
        self.assertEqual(self.verify(), summary)
        self.assertEqual(len(self.requests), 52)
        self.assertNotIn('fake-test-key', (self.out/'calls.jsonl').read_text())
        calls = f.rows(self.out/'calls.jsonl')
        for draft in ('GR-M01', 'GR-M02'):
            a,b = [next(c['request'] for c in calls if c['draft_id']==draft and c['stage']==arm) for arm in g.ARMS]
            av = json.loads(a.pop('input')[0]['content']); bv = json.loads(b.pop('input')[0]['content'])
            self.assertEqual(a,b)
            self.assertTrue(av.pop('validated_cue_feedback'))
            self.assertEqual(av,bv)
        self.assertEqual(sum(r['flagged'] for r in f.rows(self.out/'outcomes.jsonl')),2)

    def test_nonflagged_and_unresolved_receive_no_rewrites(self):
        def transport(*args):
            return {'classification': 'unresolved'}, None
        _, summary = self.run_mock(transport)
        self.assertEqual(summary['calls'], 48)
        self.assertEqual(summary['flagged'], 0)
        self.assertEqual(summary['screening'], {'unresolved':48})
        self.assertEqual(self.verify(),summary)

    def test_failed_arm_is_not_retried(self):
        def transport(provider, body, key):
            if isinstance(body['input'], list) and 'validated_cue_feedback' in json.loads(body['input'][0]['content']):
                return {'status':'incomplete'}, None
            return self.transport(provider,body,key)
        _, summary = self.run_mock(transport)
        self.assertEqual(summary['calls'], 52)
        self.assertEqual(summary['arms']['cue_specific']['failed'],2)
        self.assertEqual(summary['arms']['generic']['valid'],2)
        self.assertEqual(summary['eligible_pairs'],0)
        self.assertEqual(self.verify(),summary)

    def test_model_mismatch(self):
        def transport(provider, body, key):
            raw,rid = self.transport(provider,body,key)
            if isinstance(body['input'],list) and 'validated_cue_feedback' in json.loads(body['input'][0]['content']):
                raw['model']='different-snapshot'
            return raw,rid
        _, summary=self.run_mock(transport)
        self.assertEqual(summary['model_mismatch_pairs'],2)
        self.assertEqual(summary['eligible_pairs'],0)
        self.assertEqual(self.verify(),summary)

    def test_terminal_failure(self):
        def transport(*args):
            raise urllib.error.HTTPError('https://example.invalid',429,'test',{},None)
        status, summary=self.run_mock(transport)
        self.assertEqual(status['state'],'stopped')
        self.assertEqual(summary['calls'],1)
        with self.assertRaisesRegex(ValueError,'incomplete'):
            self.verify()

    def test_freeze_seal_and_budget_and_existing_output(self):
        with self.assertRaisesRegex(ValueError,'SHA-256'):
            self.run_mock(expected='wrong')
        with self.assertRaisesRegex(ValueError,'budget'):
            self.run_mock(budget=143)
        self.assertEqual(self.requests,[])
        self.run_mock()
        with self.assertRaises(FileExistsError):
            self.run_mock()

    def test_tamper_and_replay(self):
        self.run_mock()
        path = self.out/'calls.jsonl'
        rows = f.rows(path); rows[0]['stage']='generic'
        path.unlink(); f.write_rows(path, rows)
        with self.assertRaisesRegex(ValueError,'artifact changed'):
            self.verify()
        # Even if file hashes are recalculated, exact-request replay rejects changed stage.
        path_status = self.out/'status.json'; status=f.load(path_status)
        status['sha256']['calls.jsonl']=f.sha(path.read_bytes())
        path_status.unlink(); f.write(path_status,status)
        with self.assertRaisesRegex(ValueError,'Replay request mismatch'):
            self.verify()

    def test_parse_rewrite(self):
        for text in ('{}','{"response":""}','{"response":"x","response":"y"}','{"response":"x","extra":1}'):
            with self.assertRaises(ValueError):
                g.parse_rewrite(fixtures.response(text))
        self.assertEqual(g.parse_rewrite(fixtures.response('{"response":"valid"}')),('valid','mock-snapshot'))


class HarnessIntegrationTests(unittest.TestCase):
    @unittest.skipUnless(all((f.ROOT / path).is_file() for path in f.DEPENDENCIES), 'requires full repository checkout')
    def test_real_detector_validation_and_matched_requests(self):
        from . import cue_routing, cue_output
        config=f.load(f.ROOT/f.PROTOCOL)
        draft={'draft_id':'test', 'prompt_group_id':'test', 'draft_model':'mock',
               'current_user_message':'What can I do next?', 'visible_history':[],
               'draft':"I'll check in tomorrow. Write a list."}
        calls=[]
        def request(stage, body):
            calls.append((stage,body))
            if stage=='detect':
                result={'status':'ok','reason':'fixture','cues':[{'cue_type':'availability',
                    'span':"I'll check in tomorrow.", 'occurrence':0,'implied_claim':'proactive contact',
                    'evidence_status':'unsupported','evidence':[{'source':'capability',
                    'reference':'can_contact_or_check_in_proactively','quote':None}], 'reason':'fixture'}]}
                return fixtures.response(json.dumps(result))
            return fixtures.response('{"response":"Write a list."}')
        outcome=g.evaluate(draft,config,g.ARMS,request,assess=cue_routing._assessment,build_state=cue_output.state)
        self.assertTrue(outcome['flagged'])
        self.assertTrue(outcome['pair_eligible'])
        self.assertEqual([s for s,_ in calls], ['detect',*g.ARMS])
        specific=json.loads(calls[1][1]['input'][0]['content']); generic=json.loads(calls[2][1]['input'][0]['content'])
        self.assertEqual(specific.pop('validated_cue_feedback')[0]['span'],"I'll check in tomorrow.")
        self.assertEqual(specific,generic)

if __name__=='__main__':
    unittest.main()
