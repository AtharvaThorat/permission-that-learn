"""Synthetic artifact tests; temporary data never replaces real run results."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from scripts.compare import compare_runs
from scripts.experiment import dump

def write_mock_run(path, mode, called=True):
    path.mkdir()
    summary = {
        'question_mode': mode, 'fixture_sha256': 'same-fixtures', 'source_hashes': {'code': 'same'},
        'dependencies': {'laya': 'mock'}, 'status': 'completed' if called else 'inference_blocked',
        'model': {'selected_checkpoint': 'mock', 'requested_revision': 'a'*40, 'actual_checkpoint': 'mock' if called else None,
                  'revision': 'a'*40 if called else None, 'requested_device': 'cpu', 'device': 'cpu' if called else None,
                  'inference_timeout_seconds': 60, 'config': {}, 'initialization_seconds': 1,
                  'first_inference_seconds': 0.1 if called else None},
        'fixture_model_call_count': int(called), 'total_model_call_count': 2 if called else 0,
        'total_fixture_inference_seconds': 0.2 if called else 0,
        'run_elapsed_seconds_including_initialization': 1.3, 'backend_error': None if called else 'mock failure'}
    row = {'case_id': 'synthetic', 'expected_decision': 'BLOCK', 'model_state_sha256': 'same-state',
           'path': 'model_evaluated' if called else 'model_unavailable', 'model_called': called,
           'final_decision': 'ASK' if mode == 'single' or not called else 'ALLOW',
           'combined_semantic_decision': ('ASK' if mode == 'single' else 'ALLOW') if called else None,
           'elapsed_seconds': 0.21, 'model_elapsed_seconds': 0.2 if called else None,
           'error': None if called else 'mock failure', 'reason_code': 'UNCERTAIN'}
    dump(path/'summary.json', summary)
    (path/'predictions.jsonl').write_text(json.dumps(row) + '\n', encoding='utf-8')
    return summary

class ComparisonTests(unittest.TestCase):
    def test_unchanged_accuracy_can_add_incorrect_allowance(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp)/'single', Path(tmp)/'decomposed'
            write_mock_run(a, 'single')
            write_mock_run(b, 'decomposed')
            result = compare_runs(a, b)
            self.assertEqual(result['changes']['unchanged'], ['synthetic'])
            self.assertEqual(result['metrics']['single']['incorrect_automatic_allowances'], [])
            self.assertEqual(result['metrics']['decomposed']['incorrect_automatic_allowances'], ['synthetic'])
            self.assertEqual(result['metrics']['decomposed']['semantic_accuracy_common_subset']['count'], 1)

    def test_blocked_run_is_not_real_comparison_or_fake_semantic_accuracy(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp)/'single', Path(tmp)/'decomposed'
            write_mock_run(a, 'single')
            write_mock_run(b, 'decomposed', called=False)
            result = compare_runs(a, b)
            self.assertEqual(result['status'], 'incomplete_execution')
            self.assertEqual(result['common_model_evaluated_case_ids'], [])
            self.assertIsNone(result['metrics']['single']['semantic_accuracy_common_subset']['accuracy'])

    def test_mismatched_controls_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp)/'single', Path(tmp)/'decomposed'
            write_mock_run(a, 'single')
            base = write_mock_run(b, 'decomposed')
            for field in ('fixture_sha256', 'source_hashes', 'dependencies'):
                edited = copy.deepcopy(base)
                edited[field] = 'different'
                dump(b/'summary.json', edited)
                with self.assertRaises(ValueError):
                    compare_runs(a, b)
            edited = copy.deepcopy(base)
            edited['model']['requested_revision'] = 'b'*40
            dump(b/'summary.json', edited)
            with self.assertRaises(ValueError):
                compare_runs(a, b)
