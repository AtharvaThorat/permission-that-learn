"""Explicit Linux environment setup, pinned asset download, and experiment configuration."""
import argparse
import json
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PROFILES = ROOT / 'configs/actors'


def profile(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    revision = data['revision']
    if len(revision) != 40 or any(c not in '0123456789abcdef' for c in revision):
        raise ValueError('Model profiles require an exact commit revision')
    return data


def install_commands(work, component, actor_profile):
    actor = profile(actor_profile)
    commands = []
    for name in (('runner', 'actor') if component == 'all' else (component,)):
        target = work / (actor.get('environment_name', 'actor') if name == 'actor' else name)
        py = target / 'bin/python'
        if not py.exists():
            if target.exists():
                raise ValueError('Incomplete environment exists; inspect it before proceeding: ' + str(target))
            commands.append([sys.executable, '-m', 'venv', str(target)])
        packages = (['-r', str(ROOT / 'requirements-evaluation-test.txt'), 'laya==0.3.28',
                     'torch==2.14.1', 'transformers==5.20.2', 'tokenizers==0.23.3',
                     'huggingface-hub==2.3.0'] if name == 'runner' else
                    ['vllm==' + actor['vllm_version'], 'transformers==' + actor['transformers_version']]
                    + (['bitsandbytes==0.48.2'] if actor['quantization'] == 'bitsandbytes' else []))
        commands += [[str(py), '-m', 'pip', 'install', *packages], [str(py), '-m', 'pip', 'check']]
    return commands


def download(cache, profiles, laya):
    from huggingface_hub import snapshot_download
    selected = [profile(p) for p in profiles]
    if laya:
        baseline = json.loads((ROOT / 'gatekeeper/model_manifest.json').read_text())['baseline']
        selected.append({'model_id': baseline['checkpoint'], 'revision': baseline['revision']})
    for item in selected:
        path = snapshot_download(item['model_id'], revision=item['revision'], cache_dir=str(cache / 'hub'),
                                 allow_patterns=['*.json', '*.safetensors', '*.txt', '*.jinja', '*.model'])
        print(json.dumps({'model': item['model_id'], 'revision': item['revision'], 'snapshot': path}))


def configure(args):
    from experiment.spec import load, plan
    if (args.clean_only and args.native_attack) or (args.task and args.all_tasks) or (args.objective and args.all_objectives):
        raise ValueError('Conflicting task/attack selection flags')
    spec = load(args.base)
    actors = {}
    original = next(iter(spec.actors.values()))
    for index, path in enumerate(args.profile):
        name = path.stem
        if name in actors:
            raise ValueError('Actor profile filenames must have distinct stems')
        p = profile(path)
        actor = original.model_copy(deep=True)
        actor.settings.serving_profile = p
        if 'chat_template_kwargs' in p:
            actor.settings.thinking_enabled = p['chat_template_kwargs'].get('enable_thinking')
        for key, source in {'model_id': 'model_id', 'served_model_name': 'served_model_name',
                            'model_revision': 'revision', 'server_version': 'vllm_version',
                            'quantization': 'quantization', 'dtype': 'dtype', 'context_limit': 'context_limit'}.items():
            setattr(actor.settings, key, p[source])
        actor.settings.template_provenance = p['model_id'] + '@' + p['revision'] + ':' + p['chat_template']
        actor.settings.local_model_path = str(args.cache_dir / 'hub' / ('models--' + p['model_id'].replace('/', '--')) / 'snapshots' / p['revision'])
        actor.settings.base_url = f'http://127.0.0.1:{args.port + (index if args.parallel else 0)}/v1'
        actor.resource_group = f'gpu{index}' if args.parallel else 'gpu0'
        actor.max_concurrent_requests = 1
        actors[name] = actor
    spec.actors = actors
    spec.name = args.name
    if args.suite:
        spec.suite = args.suite
        spec.wall.ptl_preset = 'STRICT_' + args.suite.upper()
    if args.seed:
        spec.seeds = args.seed
    spec.repetitions = args.repetitions
    if args.task:
        spec.clean_tasks = args.task
    from agentdojo.task_suite.load_suites import get_suite
    native = get_suite(spec.benchmark_version, spec.suite)
    if args.all_tasks:
        spec.clean_tasks = sorted(native.user_tasks)
    if args.native_attack:
        from integrations.agentdojo.discovery import materialize
        objectives = sorted(native.injection_tasks) if args.all_objectives else args.objective
        if not objectives:
            raise ValueError('Select --objective or --all-objectives for native attacks')
        spec.attacks = materialize(spec.suite, args.native_attack, spec.clean_tasks, objectives)
        spec.attack_panel = 'native:' + args.native_attack + '@' + spec.agentdojo_revision
    elif args.objective or args.all_objectives:
        raise ValueError('Objectives require --native-attack')
    if args.attacked_only:
        if not spec.attacks:
            raise ValueError('Attacked-only selection requires explicit attacks')
        spec.clean_tasks = []
    if args.clean_only:
        spec.attacks = []
    if args.mode:
        spec.modes = args.mode
    spec.gatekeeper.cache_dir = str(args.cache_dir)
    if args.gate_max_input_tokens is not None:
        spec.gatekeeper.max_input_tokens = args.gate_max_input_tokens
    if args.gate_timeout is not None:
        spec.gatekeeper.timeout_seconds = args.gate_timeout
    if args.gate_input_profile:
        spec.gatekeeper.input_profile = args.gate_input_profile
    spec.limits.sequential_models = not args.parallel
    spec.limits.global_episodes = len(actors) if args.parallel else 1
    spec.limits.resource_groups = {a.resource_group: 1 for a in actors.values()}
    if args.parallel:
        jobs = len(actors) * len(spec.seeds) * (len(spec.clean_tasks) + len(spec.attacks)) * len(spec.modes)
        spec.limits.pending_queue = max(spec.limits.pending_queue, min(10000, jobs))
    spec = type(spec).model_validate(spec.model_dump())
    resolved = plan(spec)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as out:
        out.write(spec.model_dump_json(indent=2) + '\n')
    print(json.dumps({'config': str(args.output), 'jobs': resolved['job_count'], 'actors': list(actors)}))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('install', help='Create/reuse separate runner and actor environments; no model download')
    p.add_argument('--work-dir', type=Path, default=Path('tmp/machine'))
    p.add_argument('--component', choices=['runner', 'actor', 'all'], default='all')
    p.add_argument('--profile', type=Path, default=PROFILES / 'qwen25-7b-t4.json')
    p.add_argument('--dry-run', action='store_true')
    p = commands.add_parser('download', help='Explicitly download selected pinned snapshots; no inference')
    p.add_argument('--cache-dir', type=Path, required=True)
    p.add_argument('--profile', type=Path, action='append', default=[])
    p.add_argument('--laya', action='store_true')
    p.add_argument('--all', action='store_true', help='All profiles in configs/actors plus baseline Laya')
    p = commands.add_parser('config', help='Generate a validated experiment spec without modifying the base')
    p.add_argument('--base', type=Path, required=True)
    p.add_argument('--profile', type=Path, action='append', required=True)
    p.add_argument('--cache-dir', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--name', default='machine-run')
    p.add_argument('--task', action='append')
    p.add_argument('--suite', choices=['workspace', 'slack', 'banking'])
    p.add_argument('--all-tasks', action='store_true')
    p.add_argument('--seed', type=int, action='append')
    p.add_argument('--repetitions', type=int, default=1)
    selection = p.add_mutually_exclusive_group()
    selection.add_argument('--clean-only', action='store_true')
    selection.add_argument('--attacked-only', action='store_true')
    p.add_argument('--native-attack', choices=['direct', 'ignore_previous', 'system_message', 'injecagent'])
    p.add_argument('--objective', action='append')
    p.add_argument('--all-objectives', action='store_true')
    p.add_argument('--mode', action='append', choices=['unprotected', 'wall_only', 'wall_gatekeeper'])
    p.add_argument('--parallel', action='store_true', help='Distinct servers/ports/resource groups; requires allocated capacity')
    p.add_argument('--port', type=int, default=8000)
    p.add_argument('--gate-max-input-tokens', type=int)
    p.add_argument('--gate-timeout', type=float)
    p.add_argument('--gate-input-profile', choices=['full_evidence', 'evidence_v2'])
    args = parser.parse_args(argv)
    if args.command == 'install':
        if not args.dry_run and (platform.system() != 'Linux' or sys.version_info[:2] != (3, 12)):
            parser.error('Installation targets Linux Python 3.12; use --dry-run to inspect elsewhere')
        for command in install_commands(args.work_dir.resolve(), args.component, args.profile):
            print(json.dumps(command), flush=True)
            if not args.dry_run:
                subprocess.run(command, cwd=ROOT, check=True)
    elif args.command == 'download':
        if args.all:
            args.profile, args.laya = sorted(PROFILES.glob('*.json')), True
        if not args.profile and not args.laya:
            parser.error('Select --profile, --laya or --all')
        download(args.cache_dir.resolve(), args.profile, args.laya)
    else:
        if not 1 <= args.port <= 65535 - (len(args.profile) - 1 if args.parallel else 0):
            parser.error('Selected ports must be within 1–65535')
        args.cache_dir = args.cache_dir.resolve()
        configure(args)


if __name__ == '__main__':
    main()
