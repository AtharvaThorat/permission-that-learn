"""Reconstruct reports from immutable attempts; never select by performance."""
import csv
import json
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from statistics import mean
from .artifacts import Result, atomic, checksum
from blackbox.actions import digest


def csv_file(path, rows):
    fields = list(dict.fromkeys(k for row in rows for k in row)) or ['status']
    with Path(path).open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def rate(values):
    scored = [x for x in values if x is not None]
    return {'value': sum(scored) / len(scored) if scored else None,
            'scored': len(scored), 'missing': len(values) - len(scored)}


def aggregate(directory, policy='earliest'):
    if policy not in ('earliest', 'latest'):
        raise ValueError('Explicit earliest/latest attempt selection required')
    directory = Path(directory)
    plan = json.loads((directory / 'plan.json').read_text())
    if plan['schema_version'] != 1:
        raise ValueError('Unsupported plan schema')
    jobs = {j['episode_spec_id']: j for j in plan['jobs']}
    if len(jobs) != len(plan['jobs']):
        raise ValueError('Duplicate planned episode')
    attempts, seen = defaultdict(list), set()
    for manifest in directory.glob('episodes/*/*/manifest.json'):
        m = json.loads(manifest.read_text())
        key, attempt = m['job']['episode_spec_id'], m['attempt_id']
        if key not in jobs or attempt in seen or m['job'] != jobs[key]:
            raise ValueError('Unknown, duplicate or conflicting attempt')
        seen.add(attempt)
        path = manifest.parent / 'result.json'
        if path.exists():
            r = Result.model_validate_json(path.read_text()).model_dump()
            if (r['episode_spec_id'], r['attempt_id'], r['run_id']) != (key, attempt, directory.name):
                raise ValueError('Result identity conflict')
            for field in ('actor', 'mode', 'identity', 'task', 'attack', 'seed', 'pair_id'):
                if r[field] != jobs[key][field]:
                    raise ValueError('Result behavior conflict: ' + field)
            for relative, expected in r['checksums'].items():
                target = (path.parent / relative).resolve()
                if not target.is_relative_to(path.parent.resolve()) or checksum(target) != expected:
                    raise ValueError('Artifact checksum mismatch')
        else:
            failure_path = manifest.parent / 'failure.json'
            failure = json.loads(failure_path.read_text()) if failure_path.exists() else {}
            r = {**jobs[key], 'attempt_id': attempt, 'started_at': m['started_at'],
                 'lifecycle': failure.get('lifecycle', 'interrupted'), 'evaluated': False, 'utility': None,
                 'attack_success': None, 'counts': {}, 'timings_seconds': {},
                 'actor_usage': None, 'backend_errors': [failure.get('error_kind', 'incomplete_attempt')]}
        r['artifact_path'] = manifest.parent.relative_to(directory).as_posix()
        attempts[key].append(r)
    selected = []
    for key, job in jobs.items():
        candidates = sorted(attempts[key], key=lambda x: (x['started_at'], x['attempt_id']))
        selected.append(candidates[0 if policy == 'earliest' else -1] if candidates else
            {**job, 'attempt_id': None, 'lifecycle': 'missing', 'evaluated': False,
             'utility': None, 'attack_success': None, 'counts': {}, 'timings_seconds': {},
             'actor_usage': None, 'backend_errors': []})
    groups = defaultdict(list)
    for r in selected:
        groups[(r['actor_profile'], r['mode'], digest(r['identity']))].append(r)
    metrics = []
    for (actor, mode, identity), rows in groups.items():
        metric = dict(actor=actor, mode=mode, configuration=identity, planned=len(rows),
                      evaluated=sum(r['evaluated'] for r in rows))
        for status in ('completed','pending_approval','budget_exceeded','infrastructure_error','cancelled','interrupted','invalid_configuration','missing'):
            metric[status] = sum(r['lifecycle'] == status for r in rows)
        for label, subset, field in (
            ('clean_utility', [r for r in rows if r['attack'] is None], 'utility'),
            ('attacked_utility', [r for r in rows if r['attack'] is not None], 'utility'),
            ('attack_success', [r for r in rows if r['attack'] is not None], 'attack_success')):
            metric.update({label+'_'+k: v for k,v in rate([r[field] for r in subset]).items()})
        for key in ('wall_denied','gatekeeper_blocked','ask','dispatches'):
            metric[key] = sum(r['counts'].get(key, 0) for r in rows)
        durations = [r['timings_seconds'].get('episode_total') for r in rows]
        metric['mean_episode_seconds'] = mean([d for d in durations if d is not None]) if any(d is not None for d in durations) else None
        usages = [r['actor_usage'] for r in rows if r['actor_usage'] is not None]
        metric['token_usage_episode_coverage'] = len(usages)
        metric['reported_total_tokens'] = sum(u['total_tokens'] for u in usages if u.get('total_tokens') is not None) if any(u.get('total_tokens') is not None for u in usages) else None
        metrics.append(metric)
    pairs = defaultdict(dict)
    for r in selected:
        pairs[r['pair_id']][r['mode']] = r
    comparisons = []
    for pair, modes in pairs.items():
        for left, right in combinations(plan['mode_breakdown'], 2):
            a, b = modes.get(left), modes.get(right)
            scored = bool(a and b and a['utility'] is not None and b['utility'] is not None)
            comparisons.append({'pair_id': pair, 'left': left, 'right': right,
                'matched_scored': scored, 'utility_difference_right_minus_left': int(b['utility'])-int(a['utility']) if scored else None})
    out = directory / 'aggregates'
    out.mkdir(exist_ok=True)
    csv_file(out/'episodes.csv', [{k:r.get(k) for k in ('episode_spec_id','attempt_id','actor_profile','mode','task','lifecycle','evaluated','utility','attack_success','artifact_path')} for r in selected])
    csv_file(out/'metrics_by_model_mode.csv', metrics)
    csv_file(out/'paired_comparisons.csv', comparisons)
    failures = Counter((r['actor_profile'], r['mode'], error) for r in selected for error in r['backend_errors'])
    csv_file(out/'failure_summary.csv', [dict(actor=a,mode=m,error=e,count=n) for (a,m,e),n in failures.items()])
    summary = {'schema_version':1,'attempt_selection':policy,'planned':len(jobs),'attempts':len(seen),
               'missing':sum(r['lifecycle']=='missing' for r in selected),'metrics':metrics}
    atomic(out/'summary.json', summary)
    (out/'REPORT.md').write_text('# Experiment results\n\nAttempt selection: '+policy+'. Missing scores remain null. Attack success means the native attacker objective was achieved; it can coexist with utility.\n\n| Actor | Mode | Planned | Evaluated | Clean utility | Attack success |\n|---|---|---:|---:|---:|---:|\n'+''.join(f"| {m['actor']} | {m['mode']} | {m['planned']} | {m['evaluated']} | {m['clean_utility_value']} | {m['attack_success_value']} |\n" for m in metrics), encoding='utf-8')
    return summary
