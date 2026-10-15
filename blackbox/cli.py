"""Offline configuration inspection only; neither command probes a model endpoint."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
from .config import load_config
from .manifest import package_versions

def readiness(config):
    missing = []
    packages = package_versions()
    for name in ('agentdojo', 'httpx', 'pydantic'):
        if packages[name] == 'missing':
            missing.append('dependency:' + name)
    if not config.agentdojo.user_task_ids:
        missing.append('explicit_user_task_ids')
    for name, path in [('policy', config.wall.policy_path), ('metadata', config.wall.metadata_path),
                       ('actor_directory', config.actor.local_model_path)]:
        if not path or not Path(path).exists():
            missing.append(name)
    # Validate policy data offline, not just file existence.
    if Path(config.wall.policy_path).is_file():
        from .permissions.wall import ReferenceWall
        ReferenceWall.from_file(config.wall.policy_path)
    if Path(config.wall.metadata_path).is_file():
        from integrations.agentdojo.context import WorkspaceFacts
        WorkspaceFacts.from_file(config.wall.metadata_path)
    if config.actor.local_model_path and Path(config.actor.local_model_path).is_dir():
        for asset in ('config.json', 'tokenizer_config.json'):
            if not (Path(config.actor.local_model_path) / asset).is_file():
                missing.append('actor_asset:' + asset)
        if not any(Path(config.actor.local_model_path).glob('*.safetensors')):
            missing.append('actor_safetensors_weights')
    elif config.actor.local_model_path:
        missing.append('actor_directory_not_directory')
    if packages['agentdojo'] != 'missing':
        dist = importlib.metadata.distribution('agentdojo')
        direct = json.loads(dist.read_text('direct_url.json') or '{}')
        if packages['agentdojo'] != config.agentdojo.distribution_version or direct.get('vcs_info', {}).get('commit_id') != config.agentdojo.source_revision:
            missing.append('exact_agentdojo_revision_provenance')
    if not config.actor.model_revision:
        missing.append('actor_revision')
    if not config.actor.template_provenance:
        missing.append('template_provenance')
    if not config.actor.server_version:
        missing.append('server_version')
    if not os.environ.get(config.actor.api_key_env):
        missing.append('actor_credential_environment_variable')
    if config.mode == 'wall_gatekeeper':
        if packages['laya'] == 'missing':
            missing.append('dependency:laya')
        from gatekeeper.config import resolve_checkpoint
        model, revision = resolve_checkpoint(profile='baseline')
        snapshot = Path(config.gatekeeper.cache_dir or '') / 'hub' / ('models--' + model.replace('/', '--')) / 'snapshots' / revision
        if not config.gatekeeper.cache_dir or not snapshot.is_dir():
            missing.append('local_laya_snapshot')
        if any(os.environ.get(name) != '1' for name in ('HF_HUB_OFFLINE', 'TRANSFORMERS_OFFLINE')):
            missing.append('offline_environment')
    if config.agentdojo.attack_file and not Path(config.agentdojo.attack_file).is_file():
        missing.append('attack_file')
    return {'status': 'configuration_readiness_only', 'missing': missing,
            'packages': packages, 'endpoint': 'not probed', 'models': 'not loaded',
            'runtime_compatibility': 'NOT VERIFIED', 'encoder_assets': 'not exhaustively inspected',
            'tool_timeout': 'cooperative deadline before/after synchronous dispatch; no forced cancellation'}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['inspect-config', 'preflight'])
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    config = load_config(args.config)
    result = readiness(config)
    if args.command == 'inspect-config':
        result['configuration'] = config.model_dump()
    print(json.dumps(result, indent=2))
    return 2 if result['missing'] else 0

if __name__ == '__main__':
    raise SystemExit(main())
