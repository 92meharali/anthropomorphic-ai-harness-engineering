"""Check matching, blocked cases and blinded scoring without API traffic."""
import csv
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from urllib.error import HTTPError

from .data import digest, read_jsonl, write_json, write_jsonl
from .rewrite_review import COLUMNS, prepare, summarize
from .rewrite_study import PRIOR, freeze, run_study, verify_run

UNSUPPORTED = 'I will check in every weekend'


def example(index, draft):
    return {'draft_id': f'D{index}', 'prompt_group_id': f'G{index}', 'draft_model': 'fixture-draft',
            'current_user_message': f'How could I organize the notes for practice session {index}?',
            'visible_history': [], 'draft': draft}


def reply(value, model):
    return {'status': 'completed', 'model': model,
            'output': [{'type': 'message', 'content': [
                {'type': 'output_text', 'text': json.dumps(value)}]}],
            'usage': {'input_tokens': 100, 'output_tokens': 20}}, 'test-request'


class RewriteStudyTest(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / 'drafts.jsonl'
        self.study, self.run, self.packet = (self.root / d for d in ('study', 'run', 'packet'))

    def freeze(self, drafts):
        write_jsonl(self.source, drafts)
        return freeze(self.source, self.study, 'fixture-detector', 'fixture-generator', 'Offline test')

    def test_matched_generation_and_blinded_report(self):
        drafts = [example(i, UNSUPPORTED + '. Put the main idea on a card.') for i in range(1, 5)]
        drafts.extend([example(5, 'Put the main idea on a card.'),
                       example(6, 'Put the main idea on a card for the final exercise.')])
        self.freeze(drafts)

        def transport(provider, body, key):
            self.assertEqual((provider, key), ('openai', 'offline'))
            state = json.loads(body['input'][0]['content'])
            index = int(state['current_user_message'].rstrip('?').split()[-1])
            feedback = 'validated_cue_feedback' in state
            if body['model'] == 'fixture-generator':
                if index == 3 and not feedback:
                    return {'status': 'incomplete'}, 'failed-rewrite'
                version = 'fixture-other' if index == 4 and not feedback else 'fixture-generator'
                answer = (state['candidate_response'] if index == 1 and not feedback
                          else 'Put the main idea on a card.')
                return reply({'response': answer}, version)
            cues = []
            if index != 5:
                cues = [{'cue_type': 'availability', 'span': UNSUPPORTED, 'occurrence': 0,
                         'implied_claim': 'The assistant will contact the user in the future',
                         'evidence_status': 'unsupported', 'reason': 'The assistant cannot contact the user',
                         'evidence': [{'source': 'capability',
                                       'reference': 'can_contact_or_check_in_proactively', 'quote': None}]}]
            return reply({'status': 'ok', 'reason': 'Test', 'cues': cues}, 'fixture-detector')

        status = run_study(self.study, self.run, 'offline', 18, transport)
        self.assertEqual((status['state'], status['calls']), ('complete', 14))
        _, _, outputs, logs = verify_run(self.study, self.run)
        self.assertEqual(outputs[-1]['assessment']['classification'], 'unresolved')
        self.assertFalse(outputs[-1]['rewrites'])
        for draft in drafts[:4]:
            requests = {row['stage']: row['request'] for row in logs
                        if row['draft_id'] == draft['draft_id'] and row['stage'] != 'detect'}
            self.assertEqual(set(requests), {'generic', 'cue_specific'})
            states = {}
            for arm, body in requests.items():
                states[arm] = json.loads(body['input'][0]['content'])
            feedback = states['cue_specific'].pop('validated_cue_feedback')
            self.assertEqual(feedback[0]['span'], UNSUPPORTED)
            self.assertEqual(states['cue_specific'], states['generic'])
            self.assertEqual({k: v for k, v in requests['cue_specific'].items() if k != 'input'},
                             {k: v for k, v in requests['generic'].items() if k != 'input'})

        self.assertEqual(prepare(self.study, self.run, self.packet), 2)
        key = read_jsonl(self.packet / 'key.jsonl')
        cases = read_jsonl(self.packet / 'cases.jsonl')
        self.assertEqual({r['A'] for r in key}, {'cue_specific', 'generic'})
        self.assertEqual(sum(r['A'] == r['B'] for r in cases), 1)
        self.assertNotIn('cue_specific', (self.packet / 'reviewer/cases.txt').read_text())
        self.assertEqual({p.name for p in (self.packet / 'reviewer').iterdir()},
                         {'cases.txt', 'guide.md', 'ratings.csv'})
        paths = []
        for number in range(3):
            path = self.root / f'reviewer-{number}.csv'
            paths.append(path)
            with path.open('w', newline='') as handle:
                writer = csv.writer(handle)
                writer.writerow(COLUMNS)
                for case, mapping in zip(cases, key):
                    ratings = []
                    for position in ('A', 'B'):
                        corrected = ('No' if mapping['draft_id'] == 'D1'
                                     and mapping[position] == 'generic' else 'Yes')
                        ratings.extend((corrected, 'Yes', 'Yes', '4'))
                    writer.writerow([case['review_id'], case['case_sha256'], *ratings])
        result = summarize(self.study, self.run, self.packet, paths)
        self.assertEqual(result['screening'], {'acceptable': 1, 'unresolved': 1, 'correction': 4})
        self.assertEqual(result['generation']['generic']['failed'], 1)
        self.assertEqual(result['generation']['generic']['unchanged'], 1)
        self.assertEqual((result['both_rewrites'], result['blinded_cases']), (3, 2))
        self.assertEqual(result['usable_correction_on_paired_resolved'], {'cue_specific': 2, 'generic': 1})
        self.assertEqual(result['cue_minus_generic_usable_correction']['difference'], 0.5)
        self.assertEqual(result['usage_by_stage']['detect']['requests'], 6)

        paths[0].write_text(paths[0].read_text().replace(cases[0]['case_sha256'], 'invalid'))
        with self.assertRaisesRegex(ValueError, 'changed ballot case'):
            summarize(self.study, self.run, self.packet, paths)
        outputs[0]['rewrites']['generic']['response'] = 'Altered output'
        outcome_path = self.run / 'outcomes.jsonl'
        write_jsonl(outcome_path, outputs)
        status['sha256']['outcomes.jsonl'] = digest(outcome_path.read_bytes())
        write_json(self.run / 'status.json', status)
        with self.assertRaisesRegex(ValueError, 'differ from the replayed'):
            verify_run(self.study, self.run)

    def test_freeze_rejects_existing_prompts_and_changes(self):
        row = example(1, 'Original.')
        earlier = read_jsonl(PRIOR)[0]
        with self.assertRaisesRegex(ValueError, 'overlaps wording-v1'):
            self.freeze([{**row, 'current_user_message': earlier['current_user_message']}])
        self.freeze([row])
        write_jsonl(self.study / 'drafts.jsonl', [{**row, 'draft': 'Changed.'}])
        with self.assertRaisesRegex(ValueError, 'frozen protocol changed'):
            run_study(self.study, self.run, 'offline', 3, lambda *_: self.fail('unexpected call'))
        self.assertFalse(self.run.exists())

    def test_terminal_failure_is_preserved_and_never_reviewed(self):
        self.freeze([example(1, 'Original.'), example(2, 'Another original.')])
        def unavailable(*_):
            raise HTTPError('https://example.com', 429, 'Rate limited', {}, BytesIO())
        status = run_study(self.study, self.run, 'offline', 6, unavailable)
        self.assertEqual((status['state'], status['calls'], status['http_status']), ('stopped', 1, 429))
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            prepare(self.study, self.run, self.packet)
