"""Exercise frozen settings and decision replay without a provider."""
import contextlib
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from . import run_wording
from .data import ROOT, digest, write_json, write_jsonl
from .held_out import ALLOCATION, CORPUS, select
from .wording_harness import prepare


def canned_reply(provider, body, key):
    state = json.loads(body['input'][0]['content'])
    if 'user_prompt' in state:
        value = {'rating': 4, 'reason': 'Test'}
    elif 'A' in state:
        value = {'preference': 'tie', 'cue_needs_correction': 'neither', 'content_preserved': True}
    else:
        value = {'status': 'ok', 'reason': 'Test', 'cues': []}
    return {'status': 'completed', 'model': 'test-model',
            'output': [{'type': 'message', 'content': [
                {'type': 'output_text', 'text': json.dumps(value)}]}]}, 'test-model'


class RunWordingTest(unittest.TestCase):
    def test_approval_binds_exact_reserved_configuration(self):
        config = {'cohort': 'held_out', 'models': {'detector': 'frozen'}}
        sha = run_wording.configuration_hash(config)
        snapshot = {'status': 'dry_run', 'configuration': config, 'configuration_sha256': sha}
        approval = {'configuration_sha256': sha, 'content_review_record': 'review',
                    'protocol_signoff_record': 'signoff'}
        with self.assertRaisesRegex(ValueError, 'content review and protocol sign-off'):
            run_wording.check_freeze(config, snapshot, None)
        with self.assertRaisesRegex(ValueError, 'Configuration differs'):
            run_wording.check_freeze({**config, 'models': {}}, snapshot, approval)
        run_wording.check_freeze(config, snapshot, approval)

    def test_equal_size_split_swap_is_rejected(self):
        spec = json.loads(ALLOCATION.read_text())
        a = spec['development_families']['memory']
        b = spec['reserved_families']['memory']
        a[0], b[0] = b[0], a[0]
        with TemporaryDirectory() as temp:
            changed = Path(temp) / 'split.json'
            write_json(changed, spec)
            with self.assertRaisesRegex(ValueError, 'approved v1 split'):
                select(CORPUS, changed)

    def test_replay_rejects_resealed_choice(self):
        source = ROOT / 'data/development_reviewed.jsonl'
        with TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()):
            root = Path(temp)
            study, output, dry = (root / name for name in ('study', 'run', 'dry'))
            prepare(source, ROOT / 'rubric/oa_protocol.json', study, 20261123)
            args = ['run_wording', '--source', str(source), '--study', str(study), '--out']
            with patch('sys.argv', args + [str(dry)]):
                run_wording.main()
            with (patch('sys.argv', args + [str(output), '--live', '--max-calls', '180',
                                           '--freeze-manifest', str(dry / 'manifest.json'),
                                           '--env-file', str(root / 'missing.env')]),
                  patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}),
                  patch.object(run_wording, 'post', canned_reply)):
                run_wording.main()
            decisions, log = run_wording.verify_run(study, source, output)
            self.assertEqual((len(decisions), len(log)), (20, 140))
            decisions[0]['choices']['full'] = 'hold'
            path = output / 'pairs.jsonl'
            write_jsonl(path, decisions)
            with self.assertRaisesRegex(ValueError, 'Completed run file changed'):
                run_wording.verify_run(study, source, output)
            path = output / 'status.json'
            seal = json.loads(path.read_text())
            seal['files_sha256']['pairs.jsonl'] = digest((output / 'pairs.jsonl').read_bytes())
            write_json(path, seal)
            with self.assertRaisesRegex(ValueError, 'do not match the replayed'):
                run_wording.verify_run(study, source, output)
