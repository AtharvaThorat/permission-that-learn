"""Validate a Person 2 unprotected-baseline configuration before running, and its run folder after.

  preflight  The configuration is the unprotected baseline the team can pair with protected runs: one
             actor whose settings, wall and gatekeeper configuration equal the frozen baseline, only the
             `unprotected` mode, attacks identical to the team attack panels in configs/blackbox/attacks/ (or to
             an extra panel given with --attack-panel), and a plan with one job per task/attack and no missing
             prerequisites. A changed template_provenance (a recorded prompt override) is reported, not failed.
             With --actor-profile, a different model is accepted when it matches that pinned profile in
             configs/actors/ and every generation setting still equals the frozen baseline.
  check-run  Every planned episode finished exactly once with intact, correctly identified artifacts; every
             episode completed and was scored; no protection was applied; every response came from the
             expected served model; attacked episodes record whether the injection reached the model.

Both commands print one line per check and exit 1 when any check fails. check-run writes its report to
--output and never modifies the run folder. Run them in the runner environment (they import the repo).

  python scripts/person2_validate_run.py preflight --config configs/experiments/pilot-panel/unprotected.json
  python scripts/person2_validate_run.py check-run --run-dir <run> --config <config> --output <file.json>
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiment.artifacts import Result, checksum  # noqa: E402
from experiment.spec import load, plan  # noqa: E402

FROZEN_BASELINE = ROOT / 'configs/experiments/frozen/unprotected.json'
# Model identity and serving fields an --actor-profile run may change; generation settings must not change.
MODEL_FIELDS = ('model_id', 'served_model_name', 'model_revision', 'server_version', 'quantization', 'dtype',
                'context_limit', 'thinking_enabled', 'local_model_path', 'serving_profile')
ATTACK_PANELS = [ROOT / 'configs/blackbox/attacks/workspace_pilot.json',
                 ROOT / 'configs/blackbox/attacks/workspace_baseline_extension.json',
                 ROOT / 'configs/blackbox/attacks/workspace_hard_tasks.json']


class Checks:
    def __init__(self):
        self.items = []

    def add(self, name, passed, detail='', failure='FAIL', note=''):
        """detail explains a failure; note is shown when the check passes."""
        self.items.append({'check': name, 'status': 'PASS' if passed else failure,
                           'detail': note if passed else detail})

    def info(self, name, detail):
        self.items.append({'check': name, 'status': 'INFO', 'detail': detail})

    @property
    def overall(self):
        statuses = {item['status'] for item in self.items}
        return 'FAIL' if 'FAIL' in statuses else 'WARN' if 'WARN' in statuses else 'PASS'

    def show(self):
        for item in self.items:
            print(f"[{item['status']}] {item['check']}" + (f": {item['detail']}" if item['detail'] else ''))
        print(f'Overall: {self.overall}')


def preflight(config_path, extra_panels=(), actor_profile=None):
    checks = Checks()
    spec, frozen = load(config_path), load(FROZEN_BASELINE)
    checks.add('Only the unprotected mode is selected', spec.modes == ['unprotected'], f'modes={spec.modes}')
    checks.add('Exactly one actor', len(spec.actors) == 1, f'actors={list(spec.actors)}')
    if len(spec.actors) != 1:
        return checks
    (profile,) = spec.actors.values()
    (frozen_profile,) = frozen.actors.values()
    # template_provenance only records which prompt was sent; a notebook prompt override changes it on purpose.
    def without_provenance(actor):
        dump = actor.model_dump()
        dump['settings'].pop('template_provenance')
        for field in (MODEL_FIELDS if actor_profile else ()):
            dump['settings'].pop(field, None)
        return dump
    checks.add('Actor settings equal the frozen baseline',
               without_provenance(profile) == without_provenance(frozen_profile),
               'differs from configs/experiments/frozen/unprotected.json', note=profile.settings.served_model_name)
    if actor_profile:
        pinned = json.loads(Path(actor_profile).read_text(encoding='utf-8'))
        settings = profile.settings
        checks.add('Actor model matches the pinned profile (model, served name, exact revision)',
                   (settings.model_id, settings.served_model_name, settings.model_revision)
                   == (pinned['model_id'], pinned['served_model_name'], pinned['revision']),
                   f'config has {settings.model_id}@{settings.model_revision}, profile {Path(actor_profile).name} '
                   f"pins {pinned['model_id']}@{pinned['revision']}", note=f"{pinned['model_id']}@{pinned['revision'][:12]}")
        checks.info('Serving precision and context',
                    f'dtype={settings.dtype} quantization={settings.quantization} context={settings.context_limit}')
    if profile.settings.template_provenance != frozen_profile.settings.template_provenance:
        checks.info('Prompt template differs from the frozen baseline (recorded override)',
                    profile.settings.template_provenance)
    checks.add('Wall, gatekeeper, budgets and benchmark equal the frozen baseline (needed for pairing)',
               all(getattr(spec, field) == getattr(frozen, field)
                   for field in ('wall', 'gatekeeper', 'budgets', 'benchmark_version', 'agentdojo_revision',
                                 'metadata', 'seeds', 'suite')),
               'differs from configs/experiments/frozen/unprotected.json')
    cases = {case['id']: case for panel in [*ATTACK_PANELS, *map(Path, extra_panels)]
             for case in json.loads(panel.read_text(encoding='utf-8'))['cases']}
    drifted = [a.id for a in spec.attacks if a.id not in cases or (a.task, a.objective, a.payloads, a.marker) != (
        cases[a.id]['user_task_id'], cases[a.id]['injection_task_id'],
        {cases[a.id]['vector']: cases[a.id]['payload']}, cases[a.id]['marker'])]
    checks.add('Attacks are identical to the team attack panels', not drifted, f'differ: {drifted}',
               note=f'{len(spec.attacks)} attacks')
    checks.add('Every attack carries an exposure marker', all(a.marker for a in spec.attacks))
    resolved = plan(spec)
    expected = len(spec.clean_tasks) + len(spec.attacks)
    counts = f"{resolved['clean_count']} clean + {resolved['attacked_count']} attacked = {resolved['job_count']}"
    checks.add('Plan has one job per clean task and attack', resolved['job_count'] == expected, counts, note=counts)
    checks.add('No missing prerequisites', not resolved['missing_prerequisites'],
               '; '.join(resolved['missing_prerequisites']))
    checks.info('Code identity', resolved['identity']['implementation'][:12])
    return checks


def check_run(run_dir, config_path):
    checks = Checks()
    run_dir = Path(run_dir)
    spec = load(config_path)
    (profile,) = spec.actors.values()
    served = profile.settings.served_model_name
    recorded_spec = json.loads((run_dir / 'spec.json').read_text(encoding='utf-8'))
    checks.add('Run used the given configuration unchanged', recorded_spec == spec.model_dump(mode='json'))

    jobs = {job['episode_spec_id']: job for job in json.loads((run_dir / 'plan.json').read_text())['jobs']}
    attempts = {}
    for manifest_path in run_dir.glob('episodes/*/*/manifest.json'):
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        attempts.setdefault(manifest['job']['episode_spec_id'], []).append(manifest_path.parent)
    def finished(key):
        return [folder for folder in attempts.get(key, []) if (folder / 'result.json').exists()]

    unknown = [key[:12] for key in attempts if key not in jobs]
    never_finished = [jobs[key]['task'] for key in jobs if not finished(key)]
    checks.add('Every planned episode has a finished attempt', not (never_finished or unknown),
               f'no finished attempt: {never_finished}; attempts not in the plan: {unknown}')
    # A resumed run keeps its interrupted attempt; reports must then choose an attempt policy explicitly.
    extra = [jobs[key]['task'] for key in jobs if len(attempts.get(key, [])) > 1]
    checks.add('One attempt per episode', not extra,
               f'more than one attempt for {extra}: aggregate with an explicit --attempt-policy', failure='WARN')

    episodes, damaged = [], []
    for key, folders in attempts.items():
        for folder in folders:
            if key not in jobs or not (folder / 'result.json').exists():
                continue
            result = Result.model_validate_json((folder / 'result.json').read_text(encoding='utf-8')).model_dump()
            job = jobs[key]
            mismatched = [field for field in ('actor', 'mode', 'identity', 'task', 'attack', 'seed', 'pair_id')
                          if result[field] != job[field]]
            corrupted = [name for name, expected in result['checksums'].items() if checksum(folder / name) != expected]
            if mismatched or corrupted or result['run_id'] != run_dir.name:
                damaged.append(f"{result['task']}: fields {mismatched} files {corrupted}")
            episodes.append((result, folder))
    checks.add('Result files are intact and match their planned job', not damaged, '; '.join(damaged))

    def label(result):
        return result['task'] + (f" + {result['attack']['id']}" if result['attack'] else '')

    not_completed = [f"{label(r)}: {r['lifecycle']}" for r, _ in episodes if r['lifecycle'] != 'completed']
    checks.add('All episodes completed', not not_completed, '; '.join(not_completed))
    unscored = [label(r) for r, _ in episodes
                if (r['attack'] is None and r['utility'] is None)
                or (r['attack'] is not None and (r['utility'] is None or r['attack_success'] is None))]
    checks.add('Every episode was scored by AgentDojo', not unscored, ', '.join(unscored))
    protected = [label(r) for r, _ in episodes
                 if any(r['counts'].get(name, 0) for name in ('wall_denied', 'gatekeeper_blocked', 'ask'))]
    checks.add('No protection was applied (unprotected mode)', not protected, ', '.join(protected))

    models, response_errors, no_responses = set(), [], []
    for result, folder in episodes:
        actor_log = folder / result['artifacts']['actor']
        responses = [json.loads(line) for line in actor_log.read_text(encoding='utf-8').splitlines()
                     if json.loads(line).get('event') == 'response'] if actor_log.exists() else []
        if not responses:
            no_responses.append(label(result))
        models.update(record.get('model') for record in responses)
        response_errors += [f"{label(result)}: {record['error']}" for record in responses if record.get('error')]
    checks.add('Every response came from the expected model', models == {served} and not no_responses,
               f'models seen={sorted(map(str, models))} expected={served}; no responses: {no_responses}',
               note=served)
    checks.add('No failed model requests', not response_errors, '; '.join(response_errors))
    uncovered = [label(r) for r, _ in episodes
                 if r['actor_usage_coverage'].get('reported_requests') != r['actor_usage_coverage'].get('requests')]
    checks.add('Token usage reported for every request', not uncovered, ', '.join(uncovered), failure='WARN')
    not_exposed = [label(r) for r, _ in episodes if r['attack'] is not None and r['attack_exposed'] is not True]
    checks.add('Injection reached the model in every attacked episode', not not_exposed,
               f'not reached: {", ".join(not_exposed)} (attack success there does not measure resistance)'
               if not_exposed else '', failure='WARN')
    tool_errors = [label(r) for r, _ in episodes if 'native_tool_error' in r['backend_errors']]
    if tool_errors:
        checks.info('Episodes where a tool returned an error to the model (model behaviour, not a run failure)',
                    ', '.join(tool_errors))

    rows = [{'task': r['task'], 'attack': r['attack']['id'] if r['attack'] else None,
             'objective': r['attack']['objective'] if r['attack'] else None, 'lifecycle': r['lifecycle'],
             'utility': r['utility'], 'attack_success': r['attack_success'], 'attack_exposed': r['attack_exposed'],
             'backend_errors': r['backend_errors'], 'attempt_id': r['attempt_id']} for r, _ in episodes]
    return checks, sorted(rows, key=lambda row: (row['attack'] is not None, row['task']))


def main():
    parser = argparse.ArgumentParser(description='Validate Person 2 unprotected-baseline runs')
    commands = parser.add_subparsers(dest='command', required=True)
    first = commands.add_parser('preflight')
    first.add_argument('--config', required=True)
    first.add_argument('--attack-panel', action='append', default=[],
                       help='extra attack panel file (cases with id, user_task_id, injection_task_id, vector, marker, payload)')
    first.add_argument('--actor-profile', help='pinned actor profile in configs/actors/ that the config may use '
                                                'instead of the frozen model')
    second = commands.add_parser('check-run')
    second.add_argument('--run-dir', required=True)
    second.add_argument('--config', required=True)
    second.add_argument('--output', type=Path, required=True, help='validation report; must be outside the run')
    args = parser.parse_args()
    if args.command == 'preflight':
        checks = preflight(args.config, args.attack_panel, args.actor_profile)
    else:
        if args.output.resolve().is_relative_to(Path(args.run_dir).resolve()):
            parser.error('--output must be outside the run folder')
        checks, rows = check_run(args.run_dir, args.config)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({'run_dir': str(args.run_dir), 'config': str(args.config),
                                           'overall': checks.overall, 'checks': checks.items, 'episodes': rows},
                                          indent=2) + '\n', encoding='utf-8')
    checks.show()
    sys.exit(1 if checks.overall == 'FAIL' else 0)


if __name__ == '__main__':
    main()
