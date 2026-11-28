"""Regression checks for paired and failure-inclusive denominators."""
import unittest

from .rewrite_report import paired_results, reviewer_checks


class RewriteReportTest(unittest.TestCase):
    def test_joint_outcome_requires_all_checks(self):
        good = {'cue_corrected': True, 'advice_preserved': True, 'warmth_preserved': True, 'oa': 4}
        self.assertIs(reviewer_checks(good, 4)['usable'], True)
        self.assertIsNone(reviewer_checks({**good, 'oa': None}, 4)['usable'])
        self.assertIs(reviewer_checks({**good, 'oa': None, 'warmth_preserved': False}, 4)['usable'], False)

    def test_rates_expose_unresolved_and_missing_pairs(self):
        config = {'review': {'majority': 2, 'reviewers': 3, 'oa_threshold': 4},
                  'primary_outcome': {'bootstrap_seed': 20261127, 'bootstrap_draws': 100}}
        key = [{'review_id': 'r1', 'A': 'generic', 'B': 'cue_specific', 'prompt_group_id': 'f1'},
               {'review_id': 'r2', 'A': 'cue_specific', 'B': 'generic', 'prompt_group_id': 'f2'}]
        good = {'cue_corrected': True, 'advice_preserved': True, 'warmth_preserved': True, 'oa': 5}
        ballots = [{'review_id': 'r1', 'A': {**good, 'oa': 3}, 'B': good} for _ in range(3)]
        ballots += [{'review_id': 'r2', 'A': good, 'B': {**good, 'oa': None}} for _ in range(3)]
        summary = {'flagged': 3, 'calls': 6, 'arms': {}, 'model_mismatch_pairs': 1, 'usage': {}}
        result = paired_results(key, ballots, summary, config)
        self.assertEqual(result['paired_resolved'], 1)
        self.assertEqual(result['pairs']['cue_only'], 1)
        self.assertEqual(result['pairs']['unresolved'], 1)
        self.assertEqual(result['primary']['cue_minus_generic'], 1)
        self.assertIsNone(result['primary']['interval_95'])
        self.assertEqual(result['all_flagged_sensitivity']['rates'], {'cue_specific': 2/3, 'generic': 0})

    def test_empty_packet_produces_coverage_without_primary_estimate(self):
        config = {'review': {}, 'primary_outcome': {'bootstrap_draws': 100, 'bootstrap_seed': 5}}
        summary = {'flagged': 1, 'calls': 2, 'arms': {}, 'model_mismatch_pairs': 0, 'usage': {}}
        result = paired_results([], [], summary, config)
        self.assertEqual(result['eligible_pairs'], 0)
        self.assertIsNone(result['primary']['cue_minus_generic'])
        self.assertEqual(result['all_flagged_sensitivity']['rates'], {'cue_specific': 0, 'generic': 0})
