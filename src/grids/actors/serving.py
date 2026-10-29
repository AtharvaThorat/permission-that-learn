"""Serve one explicit local actor profile; downloading requires a separate opt-in."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys


def command(profile, model_path, port):
    args = [sys.executable, '-m', 'vllm.entrypoints.openai.api_server',
            '--model', str(model_path), '--tokenizer', str(model_path),
            '--served-model-name', profile['served_model_name'], '--host', '127.0.0.1',
            '--port', str(port), '--dtype', profile['dtype'],
            '--max-model-len', str(profile['context_limit']),
            '--max-num-seqs', str(profile['max_num_seqs']),
            '--gpu-memory-utilization', str(profile['gpu_memory_utilization']),
            '--enable-auto-tool-choice', '--tool-call-parser', profile['tool_call_parser']]
    if profile['quantization']:
        args += ['--quantization', profile['quantization']]
    if profile['enforce_eager']:
        args.append('--enforce-eager')
    if profile.get('reasoning_parser'):
        args += ['--reasoning-parser', profile['reasoning_parser']]
    if profile.get('chat_template_kwargs'):
        args += ['--default-chat-template-kwargs', json.dumps(profile['chat_template_kwargs'])]
    for key in ('tokenizer_mode', 'config_format', 'load_format'):
        if profile.get(key):
            args += ['--' + key.replace('_', '-'), profile[key]]
    return args


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True, type=Path)
    parser.add_argument('--cache-dir', required=True, type=Path)
    parser.add_argument('--download-assets', action='store_true')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args(argv)
    from grids.actors.profiles import load_profile
    profile = load_profile(args.profile)
    if not os.environ.get('GRIDS_ACTOR_API_KEY'):
        parser.error('Set GRIDS_ACTOR_API_KEY for the loopback server')
    for package in ('vllm', 'transformers'):
        if importlib.metadata.version(package) != profile[package + '_version']:
            raise RuntimeError('PROFILE_PACKAGE_MISMATCH: ' + package)
    from vllm.tool_parsers import ToolParserManager
    ToolParserManager.get_tool_parser(profile['tool_call_parser'])
    from huggingface_hub import snapshot_download
    path = snapshot_download(profile['model_id'], revision=profile['revision'],
        cache_dir=str(args.cache_dir / 'hub'), local_files_only=not args.download_assets,
        allow_patterns=['*.json', '*.safetensors', '*.txt', '*.jinja', '*.model*'])
    env = {**os.environ, 'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
           'VLLM_API_KEY': os.environ['GRIDS_ACTOR_API_KEY']}
    raise SystemExit(subprocess.call(command(profile, path, args.port), env=env))


if __name__ == '__main__':
    main()
