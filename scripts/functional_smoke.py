"""One clean task, at most three modes; no benchmark panel or sweep."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def specification(profile, cache, task, modes, base_url, gate_max_input_tokens=None):
    from experiment.spec import load
    spec = load(ROOT / 'configs/experiments/frozen/unprotected.json')
    actor = next(iter(spec.actors.values()))
    actor.settings.model_id = profile['model_id']
    actor.settings.served_model_name = profile['served_model_name']
    actor.settings.model_revision = profile['revision']
    actor.settings.local_model_path = str(cache.resolve() / 'hub' / ('models--' + profile['model_id'].replace('/', '--')) / 'snapshots' / profile['revision'])
    actor.settings.server_version = profile['vllm_version']
    actor.settings.template_provenance = profile['model_id'] + '@' + profile['revision'] + ':' + profile['chat_template']
    actor.settings.quantization = profile['quantization']
    actor.settings.dtype = profile['dtype']
    actor.settings.context_limit = profile['context_limit']
    actor.settings.base_url = base_url
    actor.settings.timeout_seconds = 180.0
    spec.actors = {'functional_actor': actor}
    spec.name = 'functional-smoke'
    spec.clean_tasks = [task]
    spec.modes = modes
    spec.gatekeeper.cache_dir = str(cache.resolve())
    spec.gatekeeper.timeout_seconds = 180.0
    spec.gatekeeper.load_timeout_seconds = 600.0
    spec.gatekeeper.max_input_tokens = gate_max_input_tokens
    spec.budgets.max_episode_seconds = 900.0
    return type(spec).model_validate(spec.model_dump())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True, type=Path)
    parser.add_argument('--cache-dir', required=True, type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'results/functional')
    parser.add_argument('--task', default='user_task_0')
    parser.add_argument('--modes', nargs='+', choices=['unprotected', 'wall_only', 'wall_gatekeeper'],
                        default=['unprotected', 'wall_only', 'wall_gatekeeper'])
    parser.add_argument('--base-url', default='http://127.0.0.1:8000/v1')
    parser.add_argument('--gate-max-input-tokens', type=int, default=None,
                        help='Explicit Laya max_len override (512–8192); default preserves checkpoint settings')
    parser.add_argument('--allow-models', action='store_true')
    args = parser.parse_args()
    if not args.allow_models:
        parser.error('Real functional checks require --allow-models')
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    from experiment.artifacts import atomic
    from experiment.store import create_run, compatible
    from experiment.services import Services
    from experiment.scheduler import schedule
    from experiment.runtime import execute
    from experiment.aggregate import aggregate
    from experiment.report import report
    profile = json.loads(args.profile.read_text())
    spec = specification(profile, args.cache_dir, args.task, args.modes, args.base_url, args.gate_max_input_tokens)
    directory = create_run(spec, args.output)
    atomic(directory / 'serving-profile.json', profile)
    packages = {}
    for name in ('agentdojo', 'laya', 'torch', 'transformers', 'tokenizers', 'huggingface-hub'):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    atomic(directory / 'runner-environment.json', {'python': platform.python_version(),
           'platform': platform.platform(), 'packages': packages})
    print('RUN_DIR=' + str(directory), flush=True)
    services = Services(spec)
    try:
        schedule(spec, compatible(directory, spec), directory,
                 lambda *a: execute(spec, services, directory, *a))
    finally:
        services.close()
        print('REPORT=' + report(directory), flush=True)
    print(json.dumps(aggregate(directory), indent=2))


if __name__ == '__main__':
    main()
