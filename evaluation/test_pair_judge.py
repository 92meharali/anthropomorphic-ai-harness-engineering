import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from evaluation import pair_judge as j

GUIDE = j.GUIDE_PATH


def pair(identifier='W0001'):
    p = {'review_id': identifier, 'prompt': 'Current user message: Help me plan.',
         'A': 'We can make a plan here.', 'B': 'I will check in tomorrow.'}
    p['pair_sha256'] = j.digest(json.dumps(p, sort_keys=True, ensure_ascii=False))
    return p


def ballot(p, pref='A', correction='B', preserved=True):
    return j.attach_ballot(p, dict(preference=pref, cue_needs_correction=correction,
                                   content_preserved=preserved))


class PairJudgeTests(unittest.TestCase):
    def test_guide_and_request_allowlist(self):
        p = pair()
        req = j.request_body('test-model', p)
        self.assertTrue(req['instructions'].endswith(j.load_guide()))
        self.assertEqual(json.loads(req['input'][0]['content']),
                         {k: p[k] for k in ('prompt', 'A', 'B')})
        self.assertEqual(set(req['text']['format']['schema']['required']), set(j.FIELDS))
        self.assertNotIn(p['pair_sha256'], json.dumps(req))
        with TemporaryDirectory() as d:
            altered = Path(d) / 'guide.md'
            altered.write_text(j.load_guide() + 'Changed.', encoding='utf-8')
            with self.assertRaises(ValueError):
                j.load_guide(altered)

    def test_changed_pair_rejected(self):
        p = pair()
        p['A'] += ' altered'
        with self.assertRaises(ValueError):
            j.request_body('test-model', p)

    def test_exact_output_schema(self):
        p = pair()
        self.assertIsNone(ballot(p, 'tie', 'neither', None)['content_preserved'])
        for bad in (1, 'true', 'null', []):
            with self.assertRaises(ValueError):
                ballot(p, preserved=bad)
        with self.assertRaises(ValueError):
            j.parse_judgments({'preference': 'A', 'cue_needs_correction': 'B',
                               'content_preserved': True, 'reason': 'extra'})

    def test_provider_failure_and_duplicate_json(self):
        p = pair()
        with self.assertRaises(ValueError):
            j.parse_openai({'status': 'incomplete'}, p)
        with self.assertRaises(ValueError):
            j.loads('{"a": 1, "a": 2}')
        raw = {'status': 'completed', 'output': [{'type': 'message', 'content': [
            {'type': 'output_text', 'text': '{"preference":"tie","cue_needs_correction":"neither","content_preserved":null}'}]}]}
        self.assertEqual(j.parse_openai(raw, p), ballot(p, 'tie', 'neither', None))

    def test_malformed_provider_output_and_refusal(self):
        p = pair()
        for output in (None, {}, [None], [{'type': 'message', 'content': None}],
                       [{'type': 'message', 'content': [None]}],
                       [{'type': 'message', 'content': [{'type': 'refusal'}]}],
                       [{'type': 'message', 'content': [{'type': 'output_text', 'text': 42}]}]):
            with self.subTest(output=output), self.assertRaises(ValueError):
                j.parse_openai({'status': 'completed', 'output': output}, p)

    def test_comparison_ties_abstentions_and_false(self):
        a, b, c = (pair('W000'+str(i)) for i in range(1, 4))
        model = [ballot(a, 'tie', 'neither', False), ballot(b, 'cannot_judge', 'cannot_judge', None), ballot(c)]
        reviewers = {
            'R01': [ballot(a, 'tie', 'neither', False), ballot(b), ballot(c, 'A')],
            'R02': [ballot(a, 'tie', 'neither', False), ballot(b), ballot(c, 'B')],
            'R03': [ballot(a, 'A', 'neither', True), ballot(b), ballot(c, 'tie')],
        }
        report = j.compare_ballots([a,b,c], model, reviewers)
        self.assertEqual(report['preference']['majority']['matches'], 1)
        self.assertEqual(report['preference']['majority']['comparable'], 1)
        self.assertEqual(report['preference']['majority']['coverage'], 1/3)
        self.assertEqual(report['content_preserved']['majority']['matches'], 2)
        with self.assertRaises(ValueError):
            j.compare_ballots([a,b,c], model[:2], reviewers)
        model[0]['pair_sha256'] = 'bad'
        with self.assertRaises(ValueError):
            j.compare_ballots([a,b,c], model, reviewers)


if __name__ == '__main__':
    unittest.main()
