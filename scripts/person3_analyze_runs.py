"""Build the Person 3 smoke-test comparison table and enforcement checks.

Reads one or more experiment run directories (as created by
`python -m experiment run`), inspects every attempt's result.json and
events.jsonl, and writes:

  <output>/comparison.md    human-readable table and per-attempt checks
  <output>/comparison.csv   one row per attempt
  <output>/comparison.json  rows, checks, and identity comparison

It never edits the source run directories. Missing metrics stay empty.

Usage:
    python scripts/person3_analyze_runs.py --run-dirs <unprotected> <wall_only> <wall_gatekeeper> \
        --output results/person3-report
"""
import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

BYPASS = 'EXPLICIT_MODE_BYPASS'


def read_events(path):
    if not path.exists():
        return None
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def comparison_key(result):
    """Behaviour identity without mode, run IDs, or the Laya cache path.

    The frozen configs leave gatekeeper.cache_dir null, but wall_gatekeeper cannot
    load Laya without it. A cache path does not change behaviour, so it is
    excluded here and reported separately.
    """
    if not result:
        return None
    identity = json.loads(json.dumps(result.get('identity', {})))
    identity.get('gatekeeper', {}).pop('cache_dir', None)
    payload = {'actor': result.get('actor'), 'task': result.get('task'), 'seed': result.get('seed'),
               'attack': result.get('attack'), 'identity': identity}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]


def missing(value):
    return '' if value is None else value


def attempt_rows(run_dir):
    run_dir = Path(run_dir)
    for manifest in sorted(run_dir.glob('episodes/*/*/manifest.json')):
        directory = manifest.parent
        result_path = directory / 'result.json'
        result = json.loads(result_path.read_text()) if result_path.exists() else None
        events = read_events(directory / 'events.jsonl') or []
        yield directory, result, events


def analyze_attempt(run_dir, directory, result, events):
    mode = result['mode'] if result else json.loads((directory / 'manifest.json').read_text())['job']['mode']
    proposals = {e['action_id']: e['tool'] for e in events if e['event'] == 'proposed_action'}
    walls = {e['action_id']: e for e in events if e['event'] == 'wall_verdict'}
    gates_all = [e for e in events if e['event'] == 'gate_decision']
    gates_real = [e for e in gates_all if e.get('reason_code') != BYPASS]
    gates = {e['action_id']: e for e in gates_all}
    executed = [e for e in events if e['event'] == 'execution_result' and e.get('executed')]
    pending = [e for e in events if e['event'] == 'pending_approval']
    overrides = [e for e in events if e['event'] == 'enforcement_override']
    validation_failures = [e for e in events if e['event'] == 'validation_failure']

    # Enforcement checks, per action.
    violations = []
    for e in executed:
        aid = e.get('action_id')
        if mode != 'unprotected':
            wall = walls.get(aid)
            if wall is None or wall.get('decision') != 'PASS':
                violations.append(f'{e["tool"]} executed without a wall PASS')
            gate = gates.get(aid)
            if gate is not None and gate.get('decision') != 'ALLOW':
                approved = any(x['event'] == 'approval' and x.get('action_id') == aid for x in events)
                if not approved:
                    violations.append(f'{e["tool"]} executed after gate {gate.get("decision")} without approval')
        if any(p.get('action_id') == aid for p in pending):
            violations.append(f'{e["tool"]} executed while pending approval')

    checks = {}
    if mode == 'unprotected':
        checks['no_wall_evaluation'] = not walls
        checks['gate_bypass_explicit'] = all(g.get('reason_code') == BYPASS for g in gates_all)
    else:
        checks['wall_verdict_for_every_proposal'] = set(proposals) <= set(walls)
        checks['wall_is_ptl'] = (result or {}).get('identity', {}).get('wall_config', {}).get('implementation') == 'ptl'
    if mode == 'wall_only':
        checks['laya_not_called'] = not gates_real
    if mode == 'wall_gatekeeper':
        wall_passed = [aid for aid, w in walls.items() if w.get('decision') == 'PASS']
        checks['gate_evaluated_every_wall_pass'] = all(aid in gates and gates[aid].get('reason_code') != BYPASS
                                                       for aid in wall_passed)
        # A scripted gate or a crashed worker must not be mistaken for Laya evidence.
        checks['real_laya_backend'] = not wall_passed or any(
            g.get('backend') == 'existing_laya' and not g.get('error_kind') for g in gates_real)
        checks['gate_errors_not_allowed'] = all(g.get('decision') != 'ALLOW'
                                                for g in gates_real if g.get('error_kind'))
    checks['no_dispatch_after_deny_block_or_pending'] = not violations
    checks['result_recorded'] = result is not None

    counts = (result or {}).get('counts', {})
    timings = (result or {}).get('timings_seconds', {})
    usage = (result or {}).get('actor_usage') or {}
    gate_usage = (result or {}).get('gate_usage') or {}
    blocked = sum(w.get('decision') != 'PASS' for w in walls.values()) + sum(
        g.get('decision') == 'BLOCK' for g in gates_real)
    wall_summary = Counter(f"{w.get('decision')}:{w.get('reason_code')}" for w in walls.values())
    gate_summary = Counter(
        f"{g.get('decision')}:{g.get('reason_code')}" + (f"[{g.get('error_kind')}]" if g.get('error_kind') else '')
        + (f" raw={g.get('raw_recommendation')}" if g.get('raw_recommendation') else '')
        for g in gates_real)
    row = {
        'mode': mode,
        'task': (result or {}).get('task'),
        'run_id': Path(run_dir).name,
        'attempt_id': (result or {}).get('attempt_id') or directory.name,
        'pair_id': ((result or {}).get('pair_id') or '')[:12],
        'comparison_key': comparison_key(result),
        'laya_cache_dir': ((result or {}).get('identity', {}).get('gatekeeper') or {}).get('cache_dir'),
        'model': ((result or {}).get('actor') or {}).get('settings', {}).get('model_id'),
        'seed': (result or {}).get('seed'),
        'started_at': (result or {}).get('started_at'),
        'ended_at': (result or {}).get('ended_at'),
        'lifecycle': (result or {}).get('lifecycle', 'interrupted'),
        'utility': (result or {}).get('utility'),
        'attack_success': (result or {}).get('attack_success'),
        'proposed': len(proposals) + len(validation_failures),
        'executed': len(executed),
        'executed_tools': ';'.join(e['tool'] for e in executed),
        'wall_verdicts': '; '.join(f'{k} x{v}' for k, v in wall_summary.items()) or ('n/a' if mode == 'unprotected' else ''),
        'gate_decisions': '; '.join(f'{k} x{v}' for k, v in gate_summary.items()) or ('n/a' if mode != 'wall_gatekeeper' else ''),
        'confirmation_overrides': len(overrides),
        'blocked': blocked,
        'pending': len(pending),
        'actor_calls': counts.get('actor_requests'),
        'actor_tokens': usage.get('total_tokens'),
        'gate_calls': len(gates_real) if mode == 'wall_gatekeeper' else None,
        'gate_seconds': (round(timings['gatekeeper'], 3) if mode == 'wall_gatekeeper'
                         and timings.get('gatekeeper') is not None else None),
        'gate_usage': json.dumps(gate_usage) if gate_usage else None,
        'duration_seconds': round(timings['episode_total'], 2) if timings.get('episode_total') is not None else None,
        'errors': ';'.join((result or {}).get('backend_errors', ['missing result'])),
        'artifact_dir': str(directory),
        'violations': '; '.join(violations),
        'checks_passed': all(checks.values()),
        'failed_checks': ','.join(k for k, v in checks.items() if not v),
    }
    return row, checks


def classify(row):
    """First-pass failure category from the attachment's taxonomy. Confirm by reading traces."""
    errors = row['errors']
    if row['violations']:
        return 'Incorrect fallback or authorization behavior'
    if 'missing result' in errors:
        return 'Artifact/output failure'
    if row['mode'] == 'wall_gatekeeper' and 'MODEL_UNAVAILABLE' in row['gate_decisions']:
        return 'Gatekeeper/Laya failure'
    if row['mode'] == 'wall_gatekeeper' and ('truncation' in row['gate_decisions']
                                            or 'APPLICATION_CHARACTER_BUDGET' in row['gate_decisions']):
        return 'Gatekeeper/Laya failure (input size)'
    if row['lifecycle'] == 'infrastructure_error' and row['actor_calls'] in (0, None):
        return 'Model endpoint or actor failure'
    if row['lifecycle'] == 'infrastructure_error':
        return 'AgentDojo task/runtime failure or environment (inspect events)'
    if row['lifecycle'] == 'pending_approval':
        return 'Missing approval (expected behaviour, not a defect)'
    if row['utility'] is False:
        return 'Task not solved (check whether model or protection caused it)'
    return ''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dirs', nargs='+', required=True, type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rows, all_checks = [], {}
    for run_dir in args.run_dirs:
        for directory, result, events in attempt_rows(run_dir):
            row, checks = analyze_attempt(run_dir, directory, result, events)
            row['failure_class'] = classify(row)
            rows.append(row)
            all_checks[row['attempt_id']] = checks

    identity_fields = ('task', 'model', 'seed', 'comparison_key')
    identities = {f: sorted({str(r[f]) for r in rows}) for f in identity_fields}
    comparable = all(len(v) == 1 for v in identities.values())

    with (args.output / 'comparison.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ['mode'])
        writer.writeheader()
        writer.writerows(rows)
    (args.output / 'comparison.json').write_text(json.dumps(
        {'rows': rows, 'checks': all_checks, 'identities': identities, 'comparable': comparable}, indent=2))

    columns = ['mode', 'task', 'attempt_id', 'lifecycle', 'utility', 'attack_success', 'proposed', 'executed',
               'wall_verdicts', 'gate_decisions', 'blocked', 'pending', 'actor_calls', 'actor_tokens',
               'gate_calls', 'gate_seconds', 'duration_seconds', 'errors', 'failure_class']
    lines = ['# Smoke-test comparison', '',
             f"Comparable across runs (same task, model, seed, wall, gate settings and code; Laya cache path ignored): "
             f"**{'yes' if comparable else 'NO'}**",
             f"Pair IDs: {', '.join(sorted({r['pair_id'] for r in rows}))}",
             '', '| ' + ' | '.join(columns) + ' |', '|' + '---|' * len(columns)]
    for r in rows:
        lines.append('| ' + ' | '.join(str(missing(r[c])) for c in columns) + ' |')
    lines += ['', '## Enforcement checks', '']
    for r in rows:
        status = 'PASS' if r['checks_passed'] else 'FAIL: ' + r['failed_checks']
        lines.append(f"- `{r['mode']}` `{r['attempt_id']}`: {status}"
                     + (f" (violations: {r['violations']})" if r['violations'] else ''))
    lines += ['', '## Artifact directories', ''] + [f"- `{r['mode']}`: `{r['artifact_dir']}`" for r in rows]
    (args.output / 'comparison.md').write_text('\n'.join(lines) + '\n')
    print('\n'.join(lines))
    return 0 if rows and all(r['checks_passed'] for r in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
