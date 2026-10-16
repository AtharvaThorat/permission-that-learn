"""Explicit clean/attacked comparisons using native AgentDojo injection scoring."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.benchmark_colab import error_details, read_lines, write_json

MODES = ('unprotected', 'wall_only', 'wall_gatekeeper')
CONDITIONS = ('clean', 'injected')


def load_panel(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    cases = data['cases']
    if data.get('schema_version') != 1 or not isinstance(cases, list) or not cases:
        raise ValueError('Invalid injection panel')
    for case in cases:
        if set(case) != {'id', 'user_task_id', 'injection_task_id', 'vector', 'marker', 'payload'}:
            raise ValueError('Invalid injection case fields')
        if not all(isinstance(value, str) and value for value in case.values()):
            raise ValueError('Injection case values must be nonempty text')
        if not re.fullmatch(r'[a-z0-9_]+', case['id']):
            raise ValueError('Invalid case ID')
        if not re.fullmatch(r'BB_INJECT_[A-Z0-9_]+', case['marker']) or case['marker'] not in case['payload']:
            raise ValueError('Unique exposure marker required in each payload')
    for key in ('id', 'marker', 'user_task_id'):
        if len({c[key] for c in cases}) != len(cases):
            raise ValueError('Duplicate case ID, marker or user task')
    return data


def validate_native(panel, suite):
    vectors = suite.get_injection_vector_defaults()
    for case in panel['cases']:
        if case['user_task_id'] not in suite.user_tasks or case['injection_task_id'] not in suite.injection_tasks:
            raise ValueError('Unknown native task in injection panel')
        if case['vector'] not in vectors:
            raise ValueError('Unknown native injection vector')
        if case['marker'] in vectors[case['vector']]:
            raise ValueError('Exposure marker already exists in clean vector')
        # Exercise native environment injection, without calling a model or a tool.
        env = suite.load_and_inject_default_environment({case['vector']: case['payload']})
        env = suite.get_user_task_by_id(case['user_task_id']).init_environment(env)
        if case['marker'] not in env.model_dump_json():
            raise ValueError('Payload absent after native task initialization')


def trials(panel):
    # Interleave modes per case so a partial deadline still provides comparisons.
    for case in panel['cases']:
        for mode in MODES:
            for condition in CONDITIONS:
                yield case, mode, condition, f"{case['id']}--{mode}--{condition}"


class ExposureActor:
    """Observe tool content at the actual actor boundary, without changing it."""
    def __init__(self, actor, path):
        self.actor, self.path = actor, path
        self.trial_id = self.marker = None
        self.submitted = self.observed = False

    def reset(self, trial_id, marker):
        self.trial_id, self.marker = trial_id, marker
        self.submitted = self.observed = False

    def record(self):
        with self.path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'trial_id': self.trial_id, 'marker_submitted': self.submitted,
                                    'injection_observed': self.observed}) + '\n')
            stream.flush()

    def respond(self, messages, tools, timeout):
        contains = bool(self.marker) and any(m.get('role') == 'tool'
            and self.marker in (m.get('content') or '') for m in messages)
        self.submitted |= contains
        self.record()
        reply = self.actor.respond(messages, tools, timeout)
        # A successful reply confirms the request containing the marker was processed.
        self.observed |= contains
        self.record()
        return reply

    def close(self):
        self.actor.close()


def worker(config_path, output, panel_path):
    from contextlib import ExitStack
    from agentdojo.benchmark import run_task_without_injection_tasks, run_task_with_injection_tasks
    from agentdojo.logging import OutputLogger
    from agentdojo.task_suite.load_suites import get_suite
    from blackbox.config import load_config
    from blackbox.contracts import Dependencies
    from blackbox.factory import build_agentdojo_pipeline
    from blackbox.manifest import create_manifest
    from integrations.agentdojo.runner import fixed_attack, verify_distribution
    panel = load_panel(panel_path)
    config = load_config(config_path)
    verify_distribution(config)
    suite = get_suite(config.agentdojo.benchmark_version, config.agentdojo.suite)
    validate_native(panel, suite)
    attacks = {c['user_task_id']: {c['injection_task_id']: {c['vector']: c['payload']}}
               for c in panel['cases']}
    attack_path = output / 'fixed-attacks.json'
    write_json(attack_path, attacks)
    write_json(output / 'native-references.json', {
        'benchmark_version': config.agentdojo.benchmark_version,
        'description': panel.get('description'),
        'cases': [dict(c, user_prompt=suite.get_user_task_by_id(c['user_task_id']).PROMPT,
                       attacker_goal=suite.get_injection_task_by_id(c['injection_task_id']).GOAL)
                  for c in panel['cases']]})
    with ExitStack() as stack:
        pipelines = {}
        for mode in MODES:
            cfg = config.model_copy(deep=True)
            cfg.mode = mode
            cfg.audit.output_directory = str(output / 'modes')
            mode_dir = output / 'modes' / mode
            mode_dir.mkdir(parents=True)
            write_json(mode_dir / 'config.json', cfg.model_dump())
            manifest = create_manifest(cfg, mode).model_dump()
            manifest['experiment'] = {'panel': '../../injection-panel.json',
                                      'conditions': list(CONDITIONS)}
            write_json(mode_dir / 'manifest.json', manifest)
            pipeline = stack.enter_context(build_agentdojo_pipeline(cfg, Dependencies(run_id=mode)))
            pipeline.actor = ExposureActor(pipeline.actor, output / 'exposure.jsonl')
            if mode == 'wall_gatekeeper':
                start = time.monotonic()
                pipeline.gate.initialize()
                pipeline.gate.gate.initialize()
                backend = pipeline.gate.gate.backend
                write_json(output / 'laya_warmup.json', {'status': 'failed' if backend.error else 'passed',
                    'error_kind': backend.error_kind, 'seconds': time.monotonic() - start,
                    'counts_toward_benchmark': False})
                if backend.error:
                    raise RuntimeError('LAYA_WARMUP_FAILED')
            pipelines[mode] = pipeline
        for case, mode, condition, trial_id in trials(panel):
            pipeline = pipelines[mode]
            attacked = condition == 'injected'
            pipeline.actor.reset(trial_id, case['marker'] if attacked else None)
            pipeline.last_episode = None
            pipeline.metadata = {'suite': suite.name, 'task_id': case['user_task_id'],
                                 'injection_task_id': case['injection_task_id'] if attacked else None}
            write_json(output / 'progress.json', {'active_trial': trial_id})
            task = suite.get_user_task_by_id(case['user_task_id'])
            utility = success = None
            failure = []
            start = time.monotonic()
            try:
                with OutputLogger(str(output / 'native')):
                    if attacked:
                        attack = fixed_attack(suite, pipeline, attack_path,
                                              [case['user_task_id']], [case['injection_task_id']])
                        utilities, successes = run_task_with_injection_tasks(suite, pipeline, task, attack,
                            output / 'native', False, [case['injection_task_id']], config.agentdojo.benchmark_version)
                        pair = (case['user_task_id'], case['injection_task_id'])
                        utility, success = utilities[pair], successes[pair]
                    else:
                        utility, _ = run_task_without_injection_tasks(suite, pipeline, task,
                            output / 'native', False, config.agentdojo.benchmark_version)
            except Exception as exc:
                failure = error_details(exc)
            episode = pipeline.last_episode
            if episode and episode.error_context:
                failure = error_details(episode.error_context)
            row = {'trial_id': trial_id, 'case': case['id'], 'mode': mode, 'condition': condition,
                'user_task_id': case['user_task_id'], 'injection_task_id': case['injection_task_id'] if attacked else None,
                'vector': case['vector'] if attacked else None, 'official_utility': utility,
                'attack_success': success, 'marker_submitted': pipeline.actor.submitted if attacked else None,
                'injection_observed': pipeline.actor.observed if attacked else None,
                'episode_id': episode.episode_id if episode else None,
                'terminal': episode.terminal if episode and utility is not None else 'native_infrastructure_failure',
                'executed_dispatches': episode.executed if episode else 0,
                'seconds': round(time.monotonic() - start, 3), 'error_chain': failure}
            with (output / 'scores.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(row) + '\n')
                stream.flush()
            print(f"{trial_id}: utility={utility}, attack_success={success}, "
                  f"exposed={row['injection_observed']}, terminal={row['terminal']}", flush=True)
    write_json(output / 'progress.json', {'active_trial': None, 'phase': 'finished'})


def report(output, panel, status, elapsed, budget):
    scores = {r['trial_id']: r for r in read_lines(output / 'scores.jsonl')}
    exposure = {r['trial_id']: r for r in read_lines(output / 'exposure.jsonl')}
    progress = json.loads((output / 'progress.json').read_text()) if (output / 'progress.json').exists() else {}
    events = [e for mode in MODES for e in read_lines(output / 'modes' / mode / 'events.jsonl')]
    rows = []
    for case, mode, condition, key in trials(panel):
        active = progress.get('active_trial') == key
        row = dict(scores.get(key) or {'trial_id': key, 'case': case['id'], 'mode': mode, 'condition': condition,
            'user_task_id': case['user_task_id'], 'injection_task_id': case['injection_task_id'] if condition == 'injected' else None,
            'official_utility': None, 'attack_success': None, 'injection_observed': None,
            'terminal': 'interrupted' if active else 'not_started', 'executed_dispatches': None,
            'seconds': None})
        if key in exposure:
            row.update({k: v for k, v in exposure[key].items() if k != 'trial_id'})
            if condition == 'clean':
                row['injection_observed'] = row['marker_submitted'] = None
        ee = [e for e in events if row.get('episode_id') and e.get('episode_id') == row['episode_id']]
        gates = [e for e in ee if e['event'] == 'gate_decision' and e.get('backend') == 'existing_laya']
        row['laya_decisions'] = dict(Counter(e['decision'] for e in gates))
        row['gate_errors'] = dict(Counter(e['error_kind'] for e in gates if e.get('error_kind')))
        row['usable_laya_predictions'] = sum(e.get('raw_recommendation') is not None and not e.get('error_kind') for e in gates)
        row['wall_reasons'] = dict(Counter(e['reason_code'] for e in ee if e['event'] == 'wall_verdict'))
        rows.append(row)
    gate_errors = dict(Counter(e['error_kind'] for e in events
                               if e['event'] == 'gate_decision' and e.get('error_kind')))
    if status == 'completed':
        if any('infrastructure' in r['terminal'] for r in rows):
            status = 'completed_with_infrastructure_errors'
        elif gate_errors:
            status = 'completed_with_gate_errors'
    metrics = {}
    for mode in MODES:
        rr = [r for r in rows if r['mode'] == mode]
        attacked = [r for r in rr if r['condition'] == 'injected' and isinstance(r['attack_success'], bool)]
        exposed = [r for r in attacked if r['injection_observed'] is True]
        metrics[mode] = {'attack_scored': len(attacked), 'attack_successes': sum(r['attack_success'] for r in attacked),
            'attack_success_rate': sum(r['attack_success'] for r in attacked) / len(attacked) if attacked else None,
            'exposed_scored': len(exposed), 'attack_success_rate_when_exposed':
                sum(r['attack_success'] for r in exposed) / len(exposed) if exposed else None}
        for condition in CONDITIONS:
            scored = [r for r in rr if r['condition'] == condition and isinstance(r['official_utility'], bool)]
            metrics[mode][condition + '_scored'] = len(scored)
            metrics[mode][condition + '_task_successes'] = sum(r['official_utility'] for r in scored)
    summary = {'status': status, 'seconds': round(elapsed, 2), 'budget_seconds': budget,
        'planned_episodes': len(rows), 'gate_error_counts': gate_errors, 'metrics_by_mode': metrics, 'tasks': rows,
        'limitations': ['Project-authored fixed attacks; not an official attack leaderboard.',
            'Exposure means a tool-result marker reached an actor request that received a response.',
            'No exposure is not evidence of semantic injection detection.',
            'Wall-only comparison separates deterministic enforcement from Laya.',
            'Pending approvals remain terminal; no automatic approval or policy relaxation.',
            'Clean security placeholder is never counted as attack success or resistance.']}
    write_json(output / 'summary.json', summary)
    def yn(value):
        return 'unscored' if value is None else ('yes' if value else 'no')
    lines = ['# AgentDojo fixed injection comparison', '',
        f"Status: **{status}**; elapsed {elapsed:.1f} s; {len(rows)} planned episodes.", '',
        '| Case / user task | Mode | Injection | Reached Qwen | Attacker succeeded | User task passed | Tools | Laya decisions / errors | Wall reasons | Terminal |',
        '|---|---|---|---|---|---|---:|---|---|---|']
    for r in rows:
        injected = r['condition'] == 'injected'
        lines.append(f"| {r['case']} / {r['user_task_id']} | {r['mode']} | {r['injection_task_id'] or 'none'} | "
            f"{yn(r['injection_observed']) if injected else 'N/A'} | {yn(r['attack_success']) if injected else 'N/A'} | "
            f"{yn(r['official_utility'])} | {r['executed_dispatches']} | {r['laya_decisions']} / {r['gate_errors']} | {r['wall_reasons']} | {r['terminal']} |")
    lines += ['', *['- ' + item for item in summary['limitations']], '',
        'Reference: `native-references.json` contains the legitimate prompts, native attacker goals, vectors and exact payloads.',
        '`native/` contains scored traces; `modes/` contains configurations, manifests and events; `exposure.jsonl` records actor exposure.']
    (output / 'REPORT.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['_worker', '_validate'])
    parser.add_argument('--panel', required=True, type=Path)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.command == '_worker':
        worker(args.config, args.output, args.panel)
    else:
        from agentdojo.task_suite.load_suites import get_suite
        panel = load_panel(args.panel)
        validate_native(panel, get_suite('v1.2.2', 'workspace'))
        print(f"Validated {len(panel['cases'])} native injection cases; {len(list(trials(panel)))} episodes.", flush=True)
