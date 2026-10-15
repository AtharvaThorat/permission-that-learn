"""Thin wrapper around pinned native benchmark entry points. Execute only later."""
import argparse
import importlib.metadata
import json
from pathlib import Path
from uuid import uuid4
from blackbox.actions import parse_json
from blackbox.cli import readiness
from blackbox.config import load_config
from blackbox.contracts import Dependencies
from blackbox.factory import build_agentdojo_pipeline
from blackbox.manifest import create_manifest

def verify_distribution(config):
    dist = importlib.metadata.distribution('agentdojo')
    if dist.version != config.agentdojo.distribution_version:
        raise RuntimeError('AgentDojo distribution version mismatch')
    direct = json.loads(dist.read_text('direct_url.json') or '{}')
    if direct.get('vcs_info', {}).get('commit_id') != config.agentdojo.source_revision:
        raise RuntimeError('Install the exact inspected AgentDojo Git revision; missing/mismatched provenance')

def fixed_attack(suite, pipeline, path, selected_users, selected_injections):
    from agentdojo.attacks.base_attacks import BaseAttack
    data = parse_json(Path(path).read_text(encoding='utf-8'))
    vectors = suite.get_injection_vector_defaults()
    for user in selected_users:
        for injection in selected_injections:
            selected = data[user][injection]
            if not isinstance(selected, dict) or not selected or set(selected) - set(vectors):
                raise ValueError('Attack file must specify nonempty native injection vectors for every selected pair')
            if any(not isinstance(v, str) for v in selected.values()):
                raise ValueError('Injection values must be text')

    class FixedFileAttack(BaseAttack):
        name = 'fixed_file'
        def attack(self, user_task, injection_task):
            # Uses explicitly supplied benchmark data; does not run a ground truth
            # pipeline, generate an attacker model response, or access GOAL labels.
            return dict(data[user_task.ID][injection_task.ID])

    return FixedFileAttack(suite, pipeline)

def run(config, *, native_raw_logs=False):
    config.require_selection()
    if not native_raw_logs:
        raise ValueError('Native AgentDojo writes raw synthetic traces; use --native-raw-logs explicitly')
    problems = readiness(config)['missing']
    if problems:
        raise ValueError('Setup incomplete: ' + ', '.join(problems))
    verify_distribution(config)
    from agentdojo.benchmark import run_task_without_injection_tasks, run_task_with_injection_tasks
    from agentdojo.logging import OutputLogger
    from agentdojo.task_suite.load_suites import get_suite
    suite = get_suite(config.agentdojo.benchmark_version, config.agentdojo.suite)
    users = config.agentdojo.user_task_ids
    injections = config.agentdojo.injection_task_ids
    if set(users) - set(suite.user_tasks) or set(injections) - set(suite.injection_tasks):
        raise ValueError('Unknown selected native task ID')
    config = config.model_copy(deep=True)
    config.audit.record_raw_content = True
    run_id = uuid4().hex
    output = Path(config.audit.output_directory) / run_id
    output.mkdir(parents=True, exist_ok=False)
    manifest = create_manifest(config, run_id)
    (output / 'manifest.json').write_text(manifest.model_dump_json(indent=2), encoding='utf-8')
    results = []
    # Shared actor/worker across episodes; new authorization ledger per query.
    with build_agentdojo_pipeline(config, Dependencies(run_id=run_id)) as pipeline:
        attack = fixed_attack(suite, pipeline, config.agentdojo.attack_file, users, injections) if config.agentdojo.attack_name else None
        with OutputLogger(str(output / 'native')):
            for user_id in users:
                task = suite.get_user_task_by_id(user_id)
                for injection_id in injections if attack else [None]:
                    pipeline.metadata = {'suite': suite.name, 'task_id': user_id, 'injection_task_id': injection_id}
                    pipeline.last_episode = None
                    if attack is None:
                        utility, security = run_task_without_injection_tasks(
                            suite, pipeline, task, output / 'native', False, config.agentdojo.benchmark_version)
                    else:
                        utilities, securities = run_task_with_injection_tasks(
                            suite, pipeline, task, attack, output / 'native', False,
                            [injection_id], config.agentdojo.benchmark_version)
                        utility, security = utilities[(user_id, injection_id)], securities[(user_id, injection_id)]
                    episode = pipeline.last_episode
                    results.append({'task_id': user_id, 'injection_task_id': injection_id,
                        'official_utility': utility, 'official_security_field': security,
                        'attack_success': security if attack else None,
                        'episode_id': episode.episode_id if episode else None,
                        'terminal': episode.terminal if episode else 'native_infrastructure_failure',
                        'executed_dispatches': episode.executed if episode else 0,
                        'evaluated_action_attempts': episode.calls if episode else 0,
                        'ask_decisions': episode.asks if episode else 0,
                        'ask_rate_denominator': 'evaluated_action_attempts (includes invalid/wall-denied attempts)',
                        'ask_rate': episode.asks / episode.calls if episode and episode.calls else None,
                        'pending_episode': episode.terminal == 'pending_approval' if episode else False,
                        'cancelled_actions': episode.cancelled if episode else 0,
                        'executed_wall_violations': None,
                        'wall_violation_metric_status': 'requires trace review; do not infer from official security score',
                        'unauthorized_automatic_allows': None, 'false_blocks': None,
                        'independent_action_labels': 'not provided'})
                    # Preserve each completed score even if a later pair fails.
                    with (output / 'scores.jsonl').open('a', encoding='utf-8') as stream:
                        stream.write(json.dumps(results[-1]) + '\n')
    print(str(output))
    return output

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--native-raw-logs', action='store_true', help='Allow native synthetic transcript/injection logging')
    args = parser.parse_args()
    run(load_config(args.config), native_raw_logs=args.native_raw_logs)

if __name__ == '__main__':
    main()
