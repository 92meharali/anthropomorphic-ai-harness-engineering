"""Offline checks for leakage, routing failures and comparison arithmetic."""
import json
import unittest
from urllib.error import HTTPError

from .judges import parse_jev, parse_openai, request_body
from .run import execute, plan


def fixture():
    return {'common': 'Judge a standalone AI response.', 'dimensions': {'OA': {
        'rubric': 'Rate overall appropriateness 1–5.',
        'criteria': {str(i): f'Anchor {i}' for i in range(1, 6)}}},
        'abstention': 'Essential information is missing.'}


def openai_reply(rating=4):
    return {'status': 'completed', 'model': 'test-only', 'output': [{'type': 'message', 'content': [
        {'type': 'output_text', 'text': json.dumps({'rating': rating, 'reason': 'Fixture only.'})}]}]}


class PilotTests(unittest.TestCase):
    def setUp(self):
        self.record = {'item_id': 'id-SENTINEL', 'prompt': 'Example prompt', 'response': 'Example response',
                       'OA_score': 'SECRET_HUMAN_SCORE', 'OA_reason': 'SECRET_HUMAN_REASON',
                       'model': 'SECRET_SOURCE_MODEL', 'failure_mode': 'SECRET_FAILURE_MODE'}

    def test_payloads_hide_labels_and_identity(self):
        for provider in ('jev', 'openai'):
            body = request_body(provider, 'chosen-model', self.record, fixture())
            content = json.dumps(body)
            self.assertNotIn('SECRET_', content)
            self.assertNotIn('SENTINEL', content)
            if provider == 'jev':
                self.assertEqual(set(body['questions']), {'oa'})
            else:
                self.assertFalse(body['store'])

    def test_jev_abstention_is_not_zero(self):
        raw = {'answers': {'oa': {'type': 'choice', 'choice': 'cannot_judge', 'confidence': 1,
                                 'probabilities': {**{x: 0 for x in '12345'}, 'cannot_judge': 1}}}}
        result = parse_jev(raw)
        self.assertIsNone(result['rating'])
        self.assertEqual(result['status'], 'cannot_judge')
        raw['answers']['oa']['probabilities']['1'] = float('nan')
        with self.assertRaises(ValueError):
            parse_jev(raw)

    def test_openai_refusal_incomplete_and_abstention_are_distinct(self):
        self.assertEqual(parse_openai({'status': 'completed', 'output': [
            {'type': 'message', 'content': [{'type': 'refusal'}]}]})['status'], 'refusal')
        self.assertEqual(parse_openai({'status': 'incomplete'})['status'], 'incomplete')
        self.assertEqual(parse_openai(openai_reply(None))['status'], 'cannot_judge')
        for value in (0, 6, True, 3.5, '4'):
            with self.assertRaises(ValueError):
                parse_openai(openai_reply(value))

    def test_transport_error_cannot_become_a_rating(self):
        job = plan([self.record], fixture(), ['openai'], {'openai': 'test-only'})[0]
        def fail(*args):
            raise HTTPError('https://example.invalid', 401, 'secret', None, None)
        result = execute(job, 'never-log-this', transport=fail)
        self.assertEqual(result['status'], 'api_error')
        self.assertIsNone(result['rating'])
        self.assertNotIn('never-log-this', json.dumps(result))

if __name__ == '__main__':
    unittest.main()
