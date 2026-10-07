"""Compare genuine evaluator artifacts; never synthesize model responses."""
import argparse
import json
from pathlib import Path
import statistics
from scripts.experiment import new_output_dir, dump

LABELS = ('ALLOW', 'ASK', 'BLOCK')

def read_run(path):
    path = Path(path)
    summary = json.loads((path / 'summary.json').read_text(encoding='utf-8'))
    rows = [json.loads(line) for line in (path / 'predictions.jsonl').read_text(encoding='utf-8').splitlines()]
    indexed = {r['case_id']: r for r in rows}
    if len(indexed) != len(rows):
        raise ValueError('Duplicate case IDs')
    return summary, indexed

def accuracy(rows, field):
    correct = sum(r.get(field) == r['expected_decision'] for r in rows)
    return {'count': len(rows), 'correct': correct, 'accuracy': correct / len(rows) if rows else None}

def matrix(rows, field):
    return {a: {b: sum(r['expected_decision'] == a and r.get(field) == b for r in rows)
                for b in LABELS} for a in LABELS}

def timings(values):
    return {'count': len(values), 'total': sum(values) if values else None,
            'median': statistics.median(values) if values else None,
            'min': min(values) if values else None, 'max': max(values) if values else None}

def compare_runs(single_dir, decomposed_dir):
    sa, a = read_run(single_dir)
    sb, b = read_run(decomposed_dir)
    if sa['question_mode'] != 'single' or sb['question_mode'] != 'decomposed':
        raise ValueError('Expected single then decomposed runs')
    if a.keys() != b.keys():
        raise ValueError('Runs contain different case IDs')
    for key in ('fixture_sha256', 'source_hashes', 'dependencies'):
        if sa[key] != sb[key]:
            raise ValueError(f'Uncontrolled comparison: {key} differs')
    for key in ('selected_checkpoint', 'requested_revision', 'requested_device', 'inference_timeout_seconds'):
        if sa['model'][key] != sb['model'][key]:
            raise ValueError(f'Uncontrolled comparison: model.{key} differs')
    for cid in a:
        if a[cid]['expected_decision'] != b[cid]['expected_decision'] or a[cid]['model_state_sha256'] != b[cid]['model_state_sha256']:
            raise ValueError('Evidence or evaluator labels differ')
        if (a[cid]['path'] == 'deterministic_short_circuit') != (b[cid]['path'] == 'deterministic_short_circuit'):
            raise ValueError('Deterministic subset changed')
        if a[cid]['path'] == 'deterministic_short_circuit' and (
            a[cid]['final_decision'], a[cid]['reason_code']) != (b[cid]['final_decision'], b[cid]['reason_code']):
            raise ValueError('Deterministic result changed')
    shared = [cid for cid in a if a[cid]['model_called'] and b[cid]['model_called']]
    actual_verified = all(s['model'].get('revision') == s['model']['requested_revision'] and
                          s['model'].get('actual_checkpoint') == s['model']['selected_checkpoint'] and
                          s['model'].get('device') == 'cpu' for s in (sa, sb))
    if actual_verified and sa['model'].get('config') != sb['model'].get('config'):
        raise ValueError('Model configurations differ')
    complete = actual_verified and all(s['status'] == 'completed' for s in (sa, sb))
    result = {'status': 'completed_real_comparison' if complete else 'incomplete_execution',
              'actual_revision_verified': actual_verified,
              'requested_revision': sa['model']['requested_revision'],
              'checkpoint': sa['model']['selected_checkpoint'],
              'single_run': str(single_dir), 'decomposed_run': str(decomposed_dir),
              'common_model_evaluated_case_ids': shared,
              'only_single_model_called': sorted(set(cid for cid in a if a[cid]['model_called']) - set(shared)),
              'only_decomposed_model_called': sorted(set(cid for cid in b if b[cid]['model_called']) - set(shared)),
              'metrics': {}, 'case_changes': []}
    for mode, rows, summary in (('single', a, sa), ('decomposed', b, sb)):
        values = list(rows.values())
        common = [rows[cid] for cid in shared]
        # Use the identical called subset, retaining errors in the accuracy denominator.
        result['metrics'][mode] = {
            'final_accuracy': accuracy(values, 'final_decision'),
            'final_confusion_matrix': matrix(values, 'final_decision'),
            'semantic_accuracy_common_subset': accuracy(common, 'combined_semantic_decision'),
            'semantic_confusion_matrix_common_subset': matrix(common, 'combined_semantic_decision'),
            'unusable_semantic_outputs_common_subset': sum(r.get('combined_semantic_decision') is None for r in common),
            'incorrect_automatic_allowances': [r['case_id'] for r in values if r['final_decision'] == 'ALLOW' and r['expected_decision'] != 'ALLOW'],
            'ask_count': sum(r['final_decision'] == 'ASK' for r in values),
            'correct_allow_case_ids': [r['case_id'] for r in values if r['final_decision'] == r['expected_decision'] == 'ALLOW'],
            'warm_complete_decision_seconds_common_subset': timings([r['elapsed_seconds'] for r in common]),
            'warm_inference_and_ipc_seconds_common_subset': timings([r['model_elapsed_seconds'] for r in common if r['model_elapsed_seconds'] is not None]),
            'initialization_seconds': summary['model']['initialization_seconds'],
            'first_smoke_inference_seconds': summary['model']['first_inference_seconds'],
            'fixture_model_call_count': summary['fixture_model_call_count'],
            'total_model_call_count_including_smoke': summary['total_model_call_count'],
            'total_fixture_inference_seconds': summary['total_fixture_inference_seconds'],
            'run_elapsed_seconds_including_initialization': summary['run_elapsed_seconds_including_initialization'],
            'errors': {r['case_id']: r['error'] for r in values if r['error']},
            'backend_error': summary['backend_error'],
        }
    for cid in a:
        correct_a = a[cid]['final_decision'] == a[cid]['expected_decision']
        correct_b = b[cid]['final_decision'] == b[cid]['expected_decision']
        change = 'improved' if correct_b and not correct_a else 'worsened' if correct_a and not correct_b else 'unchanged'
        result['case_changes'].append({'case_id': cid, 'expected': a[cid]['expected_decision'],
            'single': a[cid]['final_decision'], 'decomposed': b[cid]['final_decision'], 'correctness_change': change})
    result['changes'] = {kind: [r['case_id'] for r in result['case_changes'] if r['correctness_change'] == kind]
                         for kind in ('improved', 'worsened', 'unchanged')}
    result['correct_allows_retained'] = sorted(set(result['metrics']['single']['correct_allow_case_ids']) &
                                                set(result['metrics']['decomposed']['correct_allow_case_ids']))
    return result

def matrix_md(value):
    return '| Expected / predicted | ALLOW | ASK | BLOCK |\n|---|---:|---:|---:|\n' + ''.join(
        f'| {label} | ' + ' | '.join(str(value[label][p]) for p in LABELS) + ' |\n' for label in LABELS)

def write_comparison(single_dir, decomposed_dir, output=None):
    result = compare_runs(single_dir, decomposed_dir)
    output = new_output_dir(output, 'comparison')
    dump(output / 'comparison.json', result)
    lines = ['# Controlled question-design comparison',
             'Development fixtures only; not a held-out benchmark or proof of safety. No threshold tuning or probability products.',
             f"Status: **{result['status']}**. Actual revision verified: **{result['actual_revision_verified']}**. "
             f"Checkpoint `{result['checkpoint']}`, revision `{result['requested_revision']}`.",
             'The single semantic label is returned by Laya. The decomposed semantic decision is computed in code from two Choice answers; '
             'it is not a directly returned model label. Each distribution remains separate.',
             'Semantic accuracy compares the computed/returned semantic decision against the fixture final label BEFORE confirmation/evidence overrides. '
             'It is a diagnostic against final labels, not separate ground truth for either decomposed question. '
             'Both modes use exactly the common model-called subset; unusable responses count as incorrect. No-output entries are outside the three-label semantic matrices.',
             f"Common model-evaluated subset ({len(result['common_model_evaluated_case_ids'])}): {result['common_model_evaluated_case_ids']}",
             'Warm complete-decision latency includes validation, IPC, both questions (decomposed), and enforcement. Initialization and first smoke inference are separate. '
             'These are sequential single runs, not a latency benchmark; no speedup is inferred. Missing timing is null, not zero. '
             'If execution is incomplete, final metrics include conservative fallbacks and are not a real question-design result.']
    for mode, metrics in result['metrics'].items():
        lines += [f'## {mode}',
                  'Final accuracy: ' + json.dumps(metrics['final_accuracy']),
                  matrix_md(metrics['final_confusion_matrix']),
                  'Semantic accuracy on the common subset: ' + json.dumps(metrics['semantic_accuracy_common_subset']),
                  matrix_md(metrics['semantic_confusion_matrix_common_subset']),
                  '```json\n' + json.dumps({k: v for k, v in metrics.items() if 'confusion_matrix' not in k}, indent=2) + '\n```']
    lines += ['## Changes', 'Improved/worsened refer to final decision correctness; unchanged can include different wrong decisions.',
              '```json\n' + json.dumps(result['changes'], indent=2) + '\n```',
              f"Correct ALLOW decisions retained: {result['correct_allows_retained']}",
              '| Case | Expected | Single | Decomposed | Correctness change |\n|---|---|---|---|---|\n' + ''.join(
                  f"| {r['case_id']} | {r['expected']} | {r['single']} | {r['decomposed']} | {r['correctness_change']} |\n" for r in result['case_changes']),
              f"Input runs: `{single_dir}` and `{decomposed_dir}`. Full raw outputs, questions, distributions, and model metadata remain in those run directories."]
    (output / 'comparison.md').write_text('\n\n'.join(lines) + '\n', encoding='utf-8')
    print(f'Comparison report: {output / "comparison.md"}')
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--single-dir', required=True, type=Path)
    parser.add_argument('--decomposed-dir', required=True, type=Path)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    result = write_comparison(args.single_dir, args.decomposed_dir, args.output_dir)
    return 0 if result['status'] == 'completed_real_comparison' else 2

if __name__ == '__main__':
    raise SystemExit(main())
