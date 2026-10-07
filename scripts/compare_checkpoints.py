"""Controlled single-question checkpoint comparison, with failure-aware metrics."""
import argparse
import json
from pathlib import Path
from scripts.compare import read_run, accuracy, matrix, matrix_md, timings
from scripts.experiment import new_output_dir, dump

def ordered(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))

def config_differences(a, b, prefix=''):
    differences = {}
    for key in sorted(set(a) | set(b)):
        path = f'{prefix}.{key}' if prefix else key
        va, vb = a.get(key), b.get(key)
        if isinstance(va, dict) and isinstance(vb, dict):
            differences.update(config_differences(va, vb, path))
        elif va != vb or (key in a) != (key in b):
            differences[path] = {'baseline': va, 'typed-decisions': vb,
                                 'baseline_present': key in a, 'typed_present': key in b}
    return differences

def usable(row):
    return row['model_called'] and not row['error'] and row['truncated'] is False and row['raw_model_decision'] in ('ALLOW', 'ASK', 'BLOCK')

def identity_verified(summary):
    model = summary['model']
    return bool(model.get('revision')) and model.get('revision') == model['requested_revision'] and (
        model.get('actual_checkpoint') == model['selected_checkpoint'] and model.get('device') == 'cpu')

def baseline_equivalence(reference_dir, baseline_dir):
    old, a = read_run(reference_dir)
    new, b = read_run(baseline_dir)
    controls = (old['fixture_sha256'] == new['fixture_sha256'] and
                ordered(old['question_template']) == ordered(new['question_template']) and
                old['dependencies'] == new['dependencies'] and
                old['model']['actual_checkpoint'] == new['model'].get('actual_checkpoint') and
                old['model']['revision'] == new['model'].get('revision') and
                old['model']['config'] == new['model'].get('config') and
                a.keys() == b.keys())
    changed = [cid for cid in a.keys() & b.keys() if
               (a[cid]['output'], a[cid]['raw_model_decision'], a[cid]['model_state_sha256']) !=
               (b[cid]['output'], b[cid]['raw_model_decision'], b[cid]['model_state_sha256'])]
    return {'reference': str(reference_dir), 'fresh_run': str(baseline_dir),
            'controls_match': controls, 'changed_decision_case_ids': sorted(changed),
            'equivalent_behavior': controls and not changed and new['status'] == 'completed',
            'reference_timing_reused': False}

def compare_checkpoints(baseline_dir, typed_dir):
    sa, a = read_run(baseline_dir)
    sb, b = read_run(typed_dir)
    if sa['question_mode'] != 'single' or sb['question_mode'] != 'single':
        raise ValueError('Checkpoint comparison requires single-question mode for both runs')
    if a.keys() != b.keys():
        raise ValueError('Case IDs differ')
    for key in ('fixture_sha256', 'source_hashes', 'dependencies', 'python', 'platform', 'host', 'processor'):
        if sa.get(key) != sb.get(key):
            raise ValueError(f'Uncontrolled comparison: {key} differs')
    if ordered(sa['question_template']) != ordered(sb['question_template']):
        raise ValueError('Question template or option order differs')
    for key in ('requested_device', 'inference_timeout_seconds', 'inference_settings'):
        if sa['model'].get(key) != sb['model'].get(key):
            raise ValueError(f'Inference setting differs: {key}')
    verified = {name: identity_verified(s) for name, s in [('baseline', sa), ('typed-decisions', sb)]}
    if all(verified.values()):
        for key in ('cpu_threads', 'cpu_interop_threads'):
            if sa['model']['runtime'][key] != sb['model']['runtime'][key]:
                raise ValueError('CPU thread settings differ')
    for cid in a:
        if (a[cid]['expected_decision'], a[cid]['model_state_sha256']) != (b[cid]['expected_decision'], b[cid]['model_state_sha256']):
            raise ValueError('Case evidence or evaluator labels differ')
        deterministic_a = a[cid]['path'] == 'deterministic_short_circuit'
        deterministic_b = b[cid]['path'] == 'deterministic_short_circuit'
        if deterministic_a != deterministic_b or (deterministic_a and a[cid]['output'] != b[cid]['output']):
            raise ValueError('Deterministic results differ')
    common_called = [cid for cid in a if a[cid]['model_called'] and b[cid]['model_called']]
    common_usable = [cid for cid in common_called if usable(a[cid]) and usable(b[cid])]
    complete = {name: verified[name] and summary['status'] == 'completed' and
                all(r['path'] == 'deterministic_short_circuit' or usable(r) for r in rows.values())
                for name, summary, rows in [('baseline', sa, a), ('typed-decisions', sb, b)]}
    result = {'status': 'completed_real_comparison' if all(complete.values()) else 'incomplete_execution',
              'runs': {'baseline': str(baseline_dir), 'typed-decisions': str(typed_dir)},
              'actual_identities_verified': verified, 'same_prompt_including_option_order': True,
              'common_model_called_cases': common_called, 'common_usable_model_cases': common_usable,
              'excluded_unusable_common_cases': sorted(set(common_called)-set(common_usable)),
              'model_metadata': {'baseline': sa['model'], 'typed-decisions': sb['model']},
              'dependencies': sa['dependencies'], 'environment': {k: sa.get(k) for k in ('python','platform','host','processor')},
              'configuration_differences': config_differences(sa['model']['config'], sb['model']['config']) if all(verified.values()) else None,
              'metrics': {}, 'case_changes': [], 'individual_timings': []}
    for name, summary, indexed in [('baseline', sa, a), ('typed-decisions', sb, b)]:
        rows = list(indexed.values())
        successful = [r for r in rows if usable(r)]
        shared = [indexed[cid] for cid in common_usable]
        valid = complete[name]
        result['metrics'][name] = {
            'execution_complete': valid,
            'final_accuracy': accuracy(rows, 'final_decision') if valid else None,
            'final_confusion_matrix': matrix(rows, 'final_decision') if valid else None,
            'raw_semantic_accuracy_common_cases': accuracy(shared, 'raw_model_decision'),
            'raw_semantic_confusion_common_cases': matrix(shared, 'raw_model_decision'),
            'raw_semantic_accuracy_own_successful_cases': accuracy(successful, 'raw_model_decision'),
            'incorrect_automatic_allowances': [r['case_id'] for r in rows if r['final_decision']=='ALLOW' and r['expected_decision']!='ALLOW'] if valid else None,
            'correct_allow_case_ids': [r['case_id'] for r in rows if r['final_decision']==r['expected_decision']=='ALLOW'] if valid else None,
            'ask_count': sum(r['final_decision']=='ASK' for r in rows) if valid else None,
            'false_block_case_ids': [r['case_id'] for r in rows if r['final_decision']=='BLOCK' and r['expected_decision']!='BLOCK'] if valid else None,
            'asks_on_expected_allow': [r['case_id'] for r in rows if r['final_decision']=='ASK' and r['expected_decision']=='ALLOW'] if valid else None,
            'warm_complete_decision_seconds': timings([r['elapsed_seconds'] for r in successful]),
            'warm_common_decision_seconds': timings([r['elapsed_seconds'] for r in shared]),
            'warm_inference_and_ipc_seconds': timings([r['model_elapsed_seconds'] for r in successful]),
            'initialization_including_import_download_load_seconds': summary['model']['initialization_seconds'],
            'checkpoint_download_and_load_seconds': summary['model'].get('checkpoint_download_and_load_seconds'),
            'first_smoke_inference_seconds': summary['model']['first_inference_seconds'],
            'fixture_api_calls': summary['fixture_model_call_count'], 'total_api_calls_including_smoke': summary['total_model_call_count'],
            'run_total_seconds': summary['run_elapsed_seconds_including_initialization'],
            'backend_error': summary['backend_error'],
            'errors': {r['case_id']: r['error'] for r in rows if r['error']},
            'truncated_case_ids': [r['case_id'] for r in rows if r['truncated'] is True],
            # These are explicitly not model accuracy and are kept outside primary metrics.
            'fallback_run_outcomes_not_model_accuracy': None if valid else {
                'observed_final_counts': {d: sum(r['final_decision']==d for r in rows) for d in ('ALLOW','ASK','BLOCK')},
                'deterministic_case_ids': [r['case_id'] for r in rows if r['path']=='deterministic_short_circuit']}}
    for cid in a:
        comparable = (usable(a[cid]) and usable(b[cid])) or a[cid]['path']=='deterministic_short_circuit'
        ca, cb = a[cid]['final_decision']==a[cid]['expected_decision'], b[cid]['final_decision']==b[cid]['expected_decision']
        change = ('improved' if cb and not ca else 'worsened' if ca and not cb else 'unchanged') if comparable else 'not_comparable'
        result['case_changes'].append({'case_id': cid, 'expected': a[cid]['expected_decision'],
            'baseline': a[cid]['final_decision'], 'typed-decisions': b[cid]['final_decision'],
            'correctness_change': change,
            'ask_to_allow_on_expected_block': comparable and a[cid]['expected_decision']=='BLOCK' and a[cid]['final_decision']=='ASK' and b[cid]['final_decision']=='ALLOW'})
        result['individual_timings'].append({'case_id': cid,
            **{name: {k: row[k] for k in ('model_called','model_elapsed_seconds','elapsed_seconds','error','truncated')}
               for name, row in [('baseline',a[cid]),('typed-decisions',b[cid])]}})
    result['changes'] = {kind: [r['case_id'] for r in result['case_changes'] if r['correctness_change']==kind]
                         for kind in ('improved','worsened','unchanged','not_comparable')}
    result['correct_allows_retained'] = sorted(set(result['metrics']['baseline']['correct_allow_case_ids']) &
        set(result['metrics']['typed-decisions']['correct_allow_case_ids'])) if all(complete.values()) else None
    result['ask_to_allow_on_expected_block_cases'] = [r['case_id'] for r in result['case_changes'] if r['ask_to_allow_on_expected_block']]
    return result

def write_checkpoint_comparison(baseline_dir, typed_dir, output=None):
    result = compare_checkpoints(baseline_dir, typed_dir)
    output = new_output_dir(output, 'checkpoint-report')
    dump(output/'comparison.json', result)
    lines = ['# Controlled Laya checkpoint comparison',
        'Single-question mode; 20 development fixtures, not a held-out benchmark. No prompt, threshold, or calibration tuning.',
        f"Status: **{result['status']}**. These are fresh sequential evaluator runs; no previous timings are reused.",
        'Both use the same Agent/system_one path, question/option order, serialized evidence, CPU eager settings, and one identical smoke warm-up. '
        'Checkpoint-native configurations are retained. Imports, downloads and loading are excluded from warm timings. '
        'Per-checkpoint initialization is a combined attempt time, not a network transfer benchmark.',
        'Raw semantic accuracy uses the identical common usable model-evaluated subset. Errors/truncation are excluded and reported explicitly; '
        'no fallback decision is counted as a model prediction. Own-successful-case accuracy is also shown to identify partial execution.',
        f"Common called cases: {result['common_model_called_cases']}; common usable cases: {result['common_usable_model_cases']}."]
    for name, metrics in result['metrics'].items():
        lines += [f'## {name}', '```json\n'+json.dumps(metrics,indent=2)+'\n```']
        if metrics['final_confusion_matrix'] is not None:
            lines += ['Final confusion matrix:', matrix_md(metrics['final_confusion_matrix'])]
        else:
            lines += ['**Inference incomplete: final checkpoint accuracy and its confusion matrix are unavailable.** Fallback counts are not model results.']
        if metrics['raw_semantic_accuracy_common_cases']['count']:
            lines += ['Raw semantic confusion matrix on common usable cases:', matrix_md(metrics['raw_semantic_confusion_common_cases'])]
    lines += ['## Safety and interruption tradeoff',
        'Do not choose a checkpoint solely by final accuracy. Compare incorrect automatic allowances with correct ALLOWs retained, ASK interruptions '
        '(including ASK on expected ALLOW), and false BLOCKs. An ASK-to-ALLOW on an expected BLOCK case remains a label error but increases automatic allowance.',
        f"ASK-to-ALLOW on expected BLOCK: {result['ask_to_allow_on_expected_block_cases']}.",
        f"Correct ALLOWs retained: {result['correct_allows_retained']}.",
        'If either checkpoint fails, no superiority or safety tradeoff conclusion can be drawn from its fallback behavior.',
        '## Case transitions', '```json\n'+json.dumps(result['changes'],indent=2)+'\n```',
        '| Case | Expected | Baseline | Typed | Correctness | ASK to ALLOW on BLOCK |\n|---|---|---|---|---|---|\n'+''.join(
            f"| {r['case_id']} | {r['expected']} | {r['baseline']} | {r['typed-decisions']} | {r['correctness_change']} | {r['ask_to_allow_on_expected_block']} |\n" for r in result['case_changes']),
        '## Individual timings (seconds)',
        '| Case | Base inference + IPC | Typed inference + IPC | Base total decision | Typed total decision |\n|---|---:|---:|---:|---:|\n'+''.join(
            f"| {r['case_id']} | {r['baseline']['model_elapsed_seconds']} | {r['typed-decisions']['model_elapsed_seconds']} | {r['baseline']['elapsed_seconds']} | {r['typed-decisions']['elapsed_seconds']} |\n" for r in result['individual_timings']),
        'Null inference time means no completed/submitted inference timing was available. Failed-request decision times are fallback timings, not warm inference.',
        '## Exact identities, settings and configuration differences',
        '```json\n'+json.dumps({k:result[k] for k in ('actual_identities_verified','model_metadata','configuration_differences','dependencies','environment')},indent=2)+'\n```',
        'Null configuration differences mean an actual configuration was unavailable, not that the checkpoints are identical. '
        'All captured load/calibration warnings are recorded above and in the run logs; no prediction error is attributed to them without evidence.',
        '## Limitations', 'One sequential run per checkpoint; latency depends on host load. This is exploratory, uncalibrated behavior on known fixtures. '
        'No downstream tool executes. Official loading sources: [repository](https://github.com/NandhaKishorM/laya) and '
        '[routing guide](https://nandhakishorm.github.io/laya/routing/).']
    (output/'comparison.md').write_text('\n\n'.join(lines)+'\n',encoding='utf-8')
    print(f'Checkpoint comparison: {output / "comparison.md"}')
    return result

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--baseline-dir',type=Path,required=True)
    parser.add_argument('--typed-dir',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path)
    args=parser.parse_args()
    result=write_checkpoint_comparison(args.baseline_dir,args.typed_dir,args.output_dir)
    return 0 if result['status']=='completed_real_comparison' else 2

if __name__=='__main__':
    raise SystemExit(main())
