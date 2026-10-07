"""Labels live here, outside the gatekeeper and its model input."""
import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import statistics
from time import perf_counter
import re
from gatekeeper.laya_adapter import LayaBackend, questions_for_mode, model_state
from gatekeeper.policy import Gatekeeper, REASONS
from gatekeeper.schemas import Request
from scripts.experiment import config, new_output_dir, source_hashes
from scripts.checkpoints import resolve_checkpoint

LABELS = ('ALLOW', 'ASK', 'BLOCK')

def dependencies():
    versions = {}
    for package in ('laya', 'torch', 'transformers', 'tokenizers', 'huggingface-hub',
                    'safetensors', 'numpy', 'pydantic', 'pydantic-core', 'pytest'):
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = None
    return versions

def stats(rows):
    return {'count': len(rows), 'correct': sum(r['correct'] for r in rows),
            'accuracy': sum(r['correct'] for r in rows) / len(rows) if rows else None}

def main(argv=None):
    settings = config()
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixtures', type=Path, default=Path('data/gatekeeper_smoke_cases.jsonl'))
    parser.add_argument('--output-dir', type=Path, help='Must not already exist; default is a unique timestamped run')
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument('--checkpoint', help='Explicit repository; known repositories use their own pinned revision')
    selection.add_argument('--checkpoint-profile', choices=('baseline', 'typed-decisions'))
    parser.add_argument('--revision', help='Explicit commit SHA for the selected repository')
    parser.add_argument('--question-mode', choices=('single', 'decomposed'), default='single')
    parser.add_argument('--timeout', type=float, default=60)
    parser.add_argument('--load-timeout', type=float, default=300)
    parser.add_argument('--cache-dir', type=Path)
    args = parser.parse_args(argv)
    if not all(0 < v < float('inf') for v in (args.timeout, args.load_timeout)):
        parser.error('Timeouts must be finite and positive')
    try:
        args.checkpoint, args.revision = resolve_checkpoint(args.checkpoint, args.revision, args.checkpoint_profile)
    except ValueError as exc:
        parser.error(str(exc))
    cases = [json.loads(line) for line in args.fixtures.read_text(encoding='utf-8').splitlines() if line.strip()]
    try:
        args.output_dir = new_output_dir(args.output_dir, args.question_mode)
    except FileExistsError:
        parser.error('Output directory already exists; choose a new directory to preserve previous runs')
    backend = LayaBackend(args.checkpoint, args.revision, args.timeout, load_timeout=args.load_timeout,
                          question_mode=args.question_mode, cache_dir=args.cache_dir)
    run_started = perf_counter()
    rows = []
    try:
        # One minimal real call precedes the fixtures; its loaded checkpoint is reused.
        backend.initialize()
        gate = Gatekeeper(backend)
        print(f"{'Case':<9} {'Expected':<9} {'Raw':<7} {'Final':<7} {'Called':<7} {'OK':<4} {'Seconds':>9}  Reason / path")
        for case in cases:
            result = gate.evaluate(case['request'])
            row = asdict(result)
            row['output'] = result.output.model_dump()
            row.update(case_id=case['case_id'], expected_decision=case['expected']['decision'],
                       question_mode=args.question_mode,
                       final_decision=result.output.decision, reason_code=result.output.reason_code,
                       correct=result.output.decision == case['expected']['decision'])
            try:
                row['model_state_sha256'] = hashlib.sha256(model_state(Request.model_validate(case['request'])).encode()).hexdigest()
            except ValueError:
                row['model_state_sha256'] = None
            rows.append(row)
            raw_label = row['raw_model_decision'] or '/'.join((row['raw_answers'] or {}).values()) or '-'
            print(f"{row['case_id']:<9} {row['expected_decision']:<9} {raw_label:<7} "
                  f"{row['final_decision']:<7} {str(row['model_called']):<7} {str(row['correct']):<4} "
                  f"{row['elapsed_seconds']:9.4f}  {row['reason_code']} / {row['path']}")
    finally:
        backend.close()
    run_seconds = perf_counter() - run_started
    matrix = {expected: {pred: sum(r['expected_decision'] == expected and r['final_decision'] == pred
                                   for r in rows) for pred in LABELS} for expected in LABELS}
    groups = {path: stats([r for r in rows if r['path'] == path]) for path in
              ('deterministic_short_circuit', 'model_evaluated', 'model_unavailable')}
    enforcement = {name: stats([r for r in rows if r['reason_code'] in reasons]) for name, reasons in {
        'validation_and_wall': {'INVALID_ACTION', 'INVALID_REQUEST', 'WALL_DENIED', 'WALL_UNVERIFIED'},
        'task_contradiction': {'TASK_MISMATCH'},
        'confirmation_and_evidence': {'CONFIRMATION_REQUIRED', 'INSUFFICIENT_EVIDENCE'},
        'model_unavailable': {'MODEL_UNAVAILABLE'},
        'other_semantic_results': {'TASK_AUTHORIZED', 'NEEDS_CLARIFICATION', 'UNCERTAIN'}}.items()}
    warm = [r['elapsed_seconds'] for r in rows if r['model_called'] and not r['error']]
    inference = [r['model_elapsed_seconds'] for r in rows if r['model_called'] and not r['error']
                 and r['model_elapsed_seconds'] is not None]
    api_counts = [r['model_call_count'] for r in rows]
    smoke_count = (backend.metadata.get('smoke') or {}).get('model_call_count', 0)
    semantic_rows = [dict(r, correct=r['combined_semantic_decision'] == r['expected_decision'])
                     for r in rows if r['model_called']]
    summary = {'status': 'inference_blocked' if backend.error else ('inference_errors' if any(r['error'] for r in rows) else 'completed'),
               'question_mode': args.question_mode, 'source_hashes': source_hashes(),
               'experiment_configuration': settings,
               'run_elapsed_seconds_including_initialization': run_seconds,
               'fixture_model_call_count': sum(api_counts) if all(n is not None for n in api_counts) else None,
               'fixture_model_call_submissions': sum(r['model_call_submissions'] for r in rows),
               'smoke_model_call_count': smoke_count,
               'total_model_call_count': sum(api_counts) + smoke_count if all(n is not None for n in api_counts + [smoke_count]) else None,
               'total_fixture_inference_seconds': sum(r['model_elapsed_seconds'] or 0 for r in rows),
               'semantic_accuracy_before_overrides': stats(semantic_rows),
               'incorrect_automatic_allowances': [r['case_id'] for r in rows if r['final_decision'] == 'ALLOW' and not r['correct']],
               'ask_count': sum(r['final_decision'] == 'ASK' for r in rows),
               'correct_allow_case_ids': [r['case_id'] for r in rows if r['final_decision'] == 'ALLOW' and r['correct']],
               'backend_error': backend.error, 'overall': stats(rows), 'groups': groups,
               'final_reason_groups': enforcement,
               'reference_distribution': dict(Counter(r['expected_decision'] for r in rows)),
               'confusion_matrix_expected_by_predicted': matrix,
               'warm_gatekeeper_seconds': {'count': len(warm), 'median': statistics.median(warm) if warm else None,
                                          'min': min(warm) if warm else None, 'max': max(warm) if warm else None},
               'warm_inference_and_ipc_seconds': {'count': len(inference),
                    'median': statistics.median(inference) if inference else None,
                    'min': min(inference) if inference else None, 'max': max(inference) if inference else None},
               'model': backend.metadata, 'python': platform.python_version(), 'platform': platform.platform(),
               'host': platform.node(), 'processor': platform.processor(),
               'dependencies': dependencies(), 'question_template': questions_for_mode(args.question_mode),
               'fixture_sha256': hashlib.sha256(args.fixtures.read_bytes()).hexdigest(),
               'incorrect_cases': [{'case_id': c['case_id'], 'request': c['request'],
                                    'expected': c['expected']['decision'], 'actual': r['final_decision']}
                                   for c, r in zip(cases, rows) if not r['correct']]}
    (args.output_dir / 'predictions.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')
    (args.output_dir / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')
    (args.output_dir / 'resolved-dependencies.txt').write_text(
        f'# Python {platform.python_version()}; unavailable packages explicitly marked\n' +
        '\n'.join(f'{k}=={v}' if v else f'# {k}: NOT INSTALLED' for k, v in summary['dependencies'].items()) + '\n', encoding='utf-8')
    table = '| Expected / predicted | ALLOW | ASK | BLOCK |\n|---|---:|---:|---:|\n' + ''.join(
        '| ' + expected + ' | ' + ' | '.join(str(matrix[expected][p]) for p in LABELS) + ' |\n' for expected in LABELS)
    report = ['# Permissions That Learn — development smoke test',
              'These 20 development fixtures are not a held-out benchmark, model training, or proof of safety. No tools execute.',
              f"Status: **{summary['status']}**. Backend error: `{backend.error}`.",
              f"Question mode: **{args.question_mode}**. Revision: `{args.revision}`. "
              'The decomposed semantic decision is computed in code, not a directly returned model label.',
              f"Final decision accuracy: **{sum(r['correct'] for r in rows)}/{len(rows)} ({summary['overall']['accuracy']:.1%})**. "
              'When inference is blocked this measures conservative fallback behavior, not Laya accuracy.',
              f"Reference distribution: `{summary['reference_distribution']}`.", table,
              '## Semantic results and calls',
              '```json\n' + json.dumps({k: summary[k] for k in ('semantic_accuracy_before_overrides',
                  'incorrect_automatic_allowances', 'ask_count', 'correct_allow_case_ids',
                  'fixture_model_call_count', 'fixture_model_call_submissions', 'smoke_model_call_count',
                  'total_model_call_count', 'total_fixture_inference_seconds', 'run_elapsed_seconds_including_initialization')}, indent=2) + '\n```',
              '## Separate paths', '```json\n' + json.dumps(groups, indent=2) + '\n```',
              'Final reason groups (wall/validation separate from task decisions):',
              '```json\n' + json.dumps(enforcement, indent=2) + '\n```',
              '`deterministic_short_circuit` means no model submission. `model_evaluated` means submitted to a loaded model worker; inspect errors for failed calls. '
              '`model_unavailable` means no model call occurred. Confirmation/evidence rules may still set a final ASK after a semantic attempt.',
              '## Timing and environment',
              f"Initialization (imports/load/download attempt): {backend.metadata['initialization_seconds']} seconds. "
              f"First minimal inference: {backend.metadata['first_inference_seconds']} seconds. "
              'Null means unavailable, not zero. Warm timings include validation, IPC, inference and enforcement; they exclude initialization.',
              '```json\n' + json.dumps({k: summary[k] for k in ('warm_gatekeeper_seconds', 'warm_inference_and_ipc_seconds', 'model', 'python', 'platform', 'dependencies')}, indent=2) + '\n```',
              '## Question template', '```json\n' + json.dumps(questions_for_mode(args.question_mode), indent=2) + '\n```',
              'The state contains only authentic_user_request, untrusted_proposed_action (tool and arguments), and verified_context. '
              'No fixture identifiers, titles, categories, expected labels, or reference rationales are passed. '
              'No confidence threshold is tuned. Class probabilities and provider confidence fields are preserved separately in raw output.',
              '## Incorrect cases and complete inputs']
    for case in summary['incorrect_cases']:
        report += [f"### {case['case_id']}: expected {case['expected']}, got {case['actual']}",
                   '```json\n' + json.dumps(case['request'], indent=2, ensure_ascii=False) + '\n```']
    if not summary['incorrect_cases']:
        report.append('None.')
    report += ['## Fixed reason templates', '\n'.join(f'- `{k}`: {v}' for k, v in REASONS.items()),
               '## API sources',
               '- https://github.com/NandhaKishorM/laya#installation-details\n'
               '- https://nandhakishorm.github.io/laya/\n'
               '- https://github.com/NandhaKishorM/laya/blob/main/laya/agent.py']
    (args.output_dir / 'report.md').write_text('\n\n'.join(report) + '\n', encoding='utf-8')
    print('\nConfusion matrix (expected rows / predicted columns):\n' + table)
    print(f"Final accuracy: {summary['overall']['accuracy']:.1%}; status: {summary['status']}")
    print('Path statistics:', json.dumps(groups))
    print(f'Report: {args.output_dir / "report.md"}')
    return 2 if backend.error or any(r['error'] for r in rows) else 0

if __name__ == '__main__':
    raise SystemExit(main())
