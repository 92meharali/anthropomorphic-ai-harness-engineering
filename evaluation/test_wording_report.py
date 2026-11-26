"""Check that a sealed HumT arm cannot silently report partial coverage."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from . import humt
from .data import digest, write_json, write_jsonl
from .wording_report import verified_humt


class WordingReportTest(unittest.TestCase):
    def test_humt_requires_complete_pinned_output(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            inputs, scores = root / 'oa_inputs.jsonl', root / 'humt.jsonl'
            write_jsonl(inputs, [{'item_id': 'W0001-A', 'response': 'An answer.'}])
            row = {'item_id': 'W0001-A', 'response_sha256': digest('An answer.'), 'humt': 0.3}
            write_jsonl(scores, [row])
            manifest = {
                'upstream_commit': humt.UPSTREAM, 'model': humt.MODEL, 'revision': humt.REVISION,
                'character_limit': humt.CHAR_LIMIT, 'dropout_samples_per_group': humt.SAMPLES,
                'seed': humt.SEED, 'seed_policy': 'base seed plus 32-bit scored-text digest prefix',
                'device': 'cpu', 'threads': 1, 'responses': 1,
                'input_sha256': digest(inputs.read_bytes()),
                'scorer_sha256': digest(Path(humt.__file__).read_bytes()),
                'output_sha256': digest(scores.read_bytes()),
                'versions': {'torch': '2.7.1', 'transformers': '4.52.4'},
            }
            manifest_path = root / 'manifest.json'
            write_json(manifest_path, manifest)
            expected = {row['item_id']}
            self.assertEqual(verified_humt(root, scores, expected), {row['item_id']: row})

            write_jsonl(scores, [])
            with self.assertRaisesRegex(ValueError, 'manifest does not match'):
                verified_humt(root, scores, expected)
            write_json(manifest_path, {**manifest, 'output_sha256': digest(scores.read_bytes())})
            with self.assertRaisesRegex(ValueError, 'cover every candidate'):
                verified_humt(root, scores, expected)
