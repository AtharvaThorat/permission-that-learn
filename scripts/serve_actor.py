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
    return args


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', required=True, type=Path)
    parser.add_argument('--cache-dir', required=True, type=Path)
    parser.add_argument('--download-assets', action='store_true')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    profile = json.loads(args.profile.read_text())
    if not os.environ.get('BLACKBOX_ACTOR_API_KEY'):
        parser.error('Set BLACKBOX_ACTOR_API_KEY for the loopback server')
    for package in ('vllm', 'transformers'):
        if importlib.metadata.version(package) != profile[package + '_version']:
            raise RuntimeError('PROFILE_PACKAGE_MISMATCH: ' + package)
    from huggingface_hub import snapshot_download
    path = snapshot_download(profile['model_id'], revision=profile['revision'],
        cache_dir=str(args.cache_dir / 'hub'), local_files_only=not args.download_assets,
        allow_patterns=['*.json', '*.safetensors', '*.txt', '*.jinja', '*.model'])
    env = {**os.environ, 'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
           'VLLM_API_KEY': os.environ['BLACKBOX_ACTOR_API_KEY']}
    raise SystemExit(subprocess.call(command(profile, path, args.port), env=env))


if __name__ == '__main__':
    main()
