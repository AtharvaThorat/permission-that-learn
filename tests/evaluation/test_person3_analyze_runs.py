"""Person 3 comparison script: per-pair-ID comparability across modes, on synthetic run folders.

No model, no AgentDojo run: each attempt is a hand-written result.json and events.jsonl in the layout the
experiment runtime writes (<run>/episodes/<episode>/<attempt>/{manifest,result}.json, events.jsonl).
"""
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts' / 'person3_analyze_runs.py'
module_spec = importlib.util.spec_from_file_location('person3_analyze_runs', SCRIPT)
analyze = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(analyze)

CASES = [('user_task_0', None), ('user_task_0', 'calendar_email'),
         ('user_task_1', None), ('user_task_1', 'calendar_delete')]


def pair_id(task, attack):
    return hashlib.sha256(f'{task}:{attack}'.encode()).hexdigest()


def write_attempt(run_dir, mode, task, attack, *, utility=True, attack_success=False, exposed=True,
                  seed=42, implementation='81f4bf1f13fd' + '0' * 52, wall='PASS', gate='ALLOW'):
    attempt = f'{mode}-{task}-{attack or "clean"}'
    directory = run_dir / 'episodes' / attempt[:16] / attempt
    directory.mkdir(parents=True)
    result = {
        'mode': mode, 'task': task, 'attempt_id': attempt, 'pair_id': pair_id(task, attack), 'seed': seed,
        'attack': {'id': attack} if attack else None,
        'attack_exposed': exposed if attack else None,
        'attack_success': attack_success if attack else None,
        'actor': {'settings': {'model_id': 'Qwen/Qwen2.5-7B-Instruct'}},
        'identity': {'implementation': implementation, 'wall_config': {'implementation': 'ptl'},
                     'gatekeeper': {'cache_dir': f'/cache/{mode}'}},
        'lifecycle': 'completed', 'utility': utility, 'counts': {'actor_requests': 2},
        'timings_seconds': {'episode_total': 1.0}, 'actor_usage': {'total_tokens': 10}, 'backend_errors': [],
    }
    (directory / 'manifest.json').write_text(json.dumps({'job': {'mode': mode}}))
    (directory / 'result.json').write_text(json.dumps(result))
    events = [{'event': 'proposed_action', 'action_id': 'a1', 'tool': 'get_day_calendar_events'}]
    if mode != 'unprotected':
        events.append({'event': 'wall_verdict', 'action_id': 'a1', 'decision': wall, 'reason_code': 'X'})
    if mode == 'wall_gatekeeper' and wall == 'PASS':
        events.append({'event': 'gate_decision', 'action_id': 'a1', 'decision': gate, 'reason_code': 'MODEL',
                       'backend': 'existing_laya'})
    else:
        events.append({'event': 'gate_decision', 'action_id': 'a1', 'decision': 'ALLOW',
                       'reason_code': analyze.BYPASS})
    if wall == 'PASS' and gate == 'ALLOW':
        events.append({'event': 'execution_result', 'action_id': 'a1', 'tool': 'get_day_calendar_events',
                       'executed': True})
    (directory / 'events.jsonl').write_text('\n'.join(json.dumps(e) for e in events) + '\n')


def three_runs(tmp_path, cases=CASES, overrides=None):
    overrides = overrides or {}
    runs = []
    for mode in ('unprotected', 'wall_only', 'wall_gatekeeper'):
        run_dir = tmp_path / mode
        for task, attack in cases:
            write_attempt(run_dir, mode, task, attack, **overrides.get((mode, task, attack), {}))
        runs.append(run_dir)
    return runs


def rows_of(runs):
    rows = []
    for run_dir in runs:
        for directory, result, events in analyze.attempt_rows(run_dir):
            row, _ = analyze.analyze_attempt(run_dir, directory, result, events)
            row['failure_class'] = analyze.classify(row)
            rows.append(row)
    return rows


def test_multi_task_runs_are_comparable_per_pair_id(tmp_path):
    overrides = {('wall_gatekeeper', 'user_task_1', 'calendar_delete'): {'gate': 'BLOCK', 'utility': False},
                 ('wall_only', 'user_task_0', 'calendar_email'): {'wall': 'DENY', 'utility': False}}
    rows = rows_of(three_runs(tmp_path, overrides=overrides))
    comparable, issues = analyze.compare_pairs(rows)
    assert comparable and issues == []
    assert len(analyze.case_rows(rows)) == 12
    totals = {t['mode']: t for t in analyze.mode_totals(rows)}
    assert totals['unprotected']['clean_utility'] == '2/2 (100.0%)'
    assert totals['wall_gatekeeper']['gate_block'] == 1 and totals['wall_gatekeeper']['gate_allow'] == 3
    assert totals['wall_only']['wall_denials'] == 1
    assert totals['wall_only']['utility_under_attack'] == '1/2 (50.0%)'
    # Not measured in this mode: stays empty, never zero.
    assert totals['unprotected']['wall_denials'] is None and totals['wall_only']['gate_allow'] is None


def test_missing_metric_stays_empty(tmp_path):
    rows = rows_of(three_runs(tmp_path, cases=[('user_task_0', 'calendar_email')],
                              overrides={(m, 'user_task_0', 'calendar_email'): {'exposed': None}
                                 for m in ('unprotected', 'wall_only', 'wall_gatekeeper')}))
    totals = analyze.mode_totals(rows)
    assert all(t['injection_reached_model'] is None and t['attack_success_when_exposed'] is None for t in totals)
    assert all(t['clean_utility'] is None for t in totals)


def test_missing_pair_and_mismatched_settings_are_not_comparable(tmp_path):
    runs = three_runs(tmp_path, overrides={('wall_only', 'user_task_1', None): {'seed': 7}})
    write_attempt(runs[2], 'wall_gatekeeper', 'user_task_2', None)  # pair absent from the other two modes
    comparable, issues = analyze.compare_pairs(rows_of(runs))
    assert not comparable
    assert any('user_task_2' in i and 'no attempt in unprotected, wall_only' in i for i in issues)
    assert any('user_task_1 + clean' in i and 'seed differs' in i for i in issues)


def test_code_identity_mismatch_is_not_comparable(tmp_path):
    runs = three_runs(tmp_path, cases=[('user_task_0', None)],
                      overrides={('wall_only', 'user_task_0', None): {'implementation': 'deadbeef' * 8}})
    comparable, issues = analyze.compare_pairs(rows_of(runs))
    assert not comparable and any('implementation differs' in i for i in issues)


def test_cli_exclude_task_applies_to_every_mode_and_leaves_runs_untouched(tmp_path):
    runs = three_runs(tmp_path)
    before = {p: p.read_bytes() for run in runs for p in run.rglob('*') if p.is_file()}
    output = tmp_path / 'report'
    completed = subprocess.run([sys.executable, str(SCRIPT), '--run-dirs', *map(str, runs),
                                '--output', str(output), '--exclude-task', 'user_task_1'],
                               capture_output=True, text=True, cwd=ROOT)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = json.loads((output / 'comparison.json').read_text())
    assert report['comparable'] and report['excluded_tasks'] == ['user_task_1']
    assert {c['task'] for c in report['cases']} == {'user_task_0'} and len(report['cases']) == 6
    assert (output / 'cases.csv').exists() and (output / 'totals.csv').exists()
    assert before == {p: p.read_bytes() for run in runs for p in run.rglob('*') if p.is_file()}
