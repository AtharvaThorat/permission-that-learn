"""Colab/Linux helper. Explicit commands install, download, test, or run one task."""
import argparse
import json
import os
from pathlib import Path
import platform
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path(__file__).resolve()
VLLM_VERSION = '0.11.0'


def execute(args, **kwargs):
    return subprocess.run([str(a) for a in args], cwd=ROOT, check=True, **kwargs)


def python_at(work, name):
    return work / name / 'bin' / 'python'


def environment(work, offline):
    env = os.environ.copy()
    env.update(HF_HOME=str(work / 'hf'), HF_HUB_CACHE=str(work / 'hf/hub'),
               HF_HUB_OFFLINE='1' if offline else '0',
               TRANSFORMERS_OFFLINE='1' if offline else '0', USE_TF='0',
               LAYA_CPU_AMP='0', TOKENIZERS_PARALLELISM='false')
    return env


def gpu_check():
    info = subprocess.check_output(['nvidia-smi', '--query-gpu=name,memory.total,compute_cap',
                                    '--format=csv,noheader,nounits'], text=True)
    name, memory, capability = [v.strip() for v in info.splitlines()[0].split(',')]
    if float(memory) < 14000 or float(capability) < 7.5:
        raise RuntimeError('This profile needs a T4-class or newer GPU with at least 14 GiB VRAM. Got: ' + info)
    print('GPU:', info.strip(), flush=True)


def install(work, full):
    names = ('gate', 'actor') if full else ('gate',)
    for name in names:
        py = python_at(work, name)
        try:
            if not py.exists():
                execute([sys.executable, '-m', 'venv', work / name])
            execute([py, '-m', 'pip', '--version'], stdout=subprocess.DEVNULL)
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Some notebook images omit ensurepip. Install the bootstrap helper
            # into our work directory instead of modifying the notebook kernel.
            bootstrap = work / 'bootstrap'
            execute([sys.executable, '-m', 'pip', 'install', '--target', bootstrap,
                     'virtualenv>=20.26,<21'])
            bootstrap_env = os.environ.copy()
            bootstrap_env['PYTHONPATH'] = str(bootstrap)
            execute([sys.executable, '-m', 'virtualenv', work / name], env=bootstrap_env)
        packages = (['-r', ROOT / 'requirements-blackbox-test.txt'] if name == 'gate'
                    else ['vllm==' + VLLM_VERSION, 'bitsandbytes>=0.46.1,<0.49'])
        execute([py, '-m', 'pip', 'install', *packages])
        if full and name == 'gate':
            execute([py, '-m', 'pip', 'install', 'torch', '--index-url', 'https://download.pytorch.org/whl/cpu'])
            execute([py, '-m', 'pip', 'install', 'laya==0.3.28', '-r', ROOT / 'requirements-blackbox-test.txt'])
        execute([py, '-m', 'pip', 'check'])
        with (work / (name + '-freeze.txt')).open('w') as out:
            execute([py, '-m', 'pip', 'freeze'], stdout=out)


def tests(work):
    execute([python_at(work, 'gate'), '-m', 'pytest', 'tests/blackbox', '-q',
             '-o', 'cache_dir=' + str(work / 'pytest-cache')])


def assets(work, revision):
    # Runs only in the gate environment, after explicit prepare. Load Laya online
    # once so its encoder/tokenizer dependencies are cached as well as its head.
    from huggingface_hub import HfApi, snapshot_download
    from laya import Agent
    manifest = json.loads((ROOT / 'gatekeeper/model_manifest.json').read_text())['baseline']
    checkpoint, laya_revision = manifest['checkpoint'], manifest['revision']
    state_path = work / 'assets.json'
    previous = json.loads(state_path.read_text()) if state_path.exists() else {}
    revision = revision or previous.get('actor_revision') or HfApi().model_info('Qwen/Qwen3-8B').sha
    if len(revision) != 40 or any(c not in '0123456789abcdef' for c in revision):
        raise ValueError('Actor revision must be a full commit SHA')
    actor_path = snapshot_download('Qwen/Qwen3-8B', revision=revision,
        allow_patterns=['*.json', '*.safetensors', '*.txt', '*.jinja', '*.model'])
    # Keep the expected pinned HF cache layout for the existing offline adapter.
    Agent(model_id_or_path=checkpoint, revision=laya_revision, device='cpu',
          fast=False, compile=False, backend='eager')
    state_path.write_text(json.dumps({'actor_path': actor_path, 'actor_revision': revision,
        'laya_checkpoint': checkpoint, 'laya_revision': laya_revision,
        'quantization': 'bitsandbytes-4bit-inflight', 'vllm_version': VLLM_VERSION}, indent=2))


def list_tasks(work):
    execute([python_at(work, 'gate'), '-c',
        "from agentdojo.task_suite.load_suites import get_suite; "
        "s=get_suite('v1.2.2','workspace'); "
        "[print(k, getattr(v, 'PROMPT', '')) for k,v in s.user_tasks.items()]"],
        env=environment(work, True))


def server_command(work, assets_data, port):
    return [str(python_at(work, 'actor')), '-m', 'vllm.entrypoints.openai.api_server',
        '--model', assets_data['actor_path'], '--tokenizer', assets_data['actor_path'],
        '--served-model-name', 'Qwen3-8B', '--host', '127.0.0.1', '--port', str(port),
        '--quantization', 'bitsandbytes', '--dtype', 'half', '--max-model-len', '8192',
        '--max-num-seqs', '1', '--gpu-memory-utilization', '0.85', '--enforce-eager',
        '--enable-auto-tool-choice', '--tool-call-parser', 'hermes']


def wait_ready(process, port, key, timeout=900):
    deadline = time.monotonic() + timeout
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('Actor server exited; inspect actor-server.log')
        request = urllib.request.Request(f'http://127.0.0.1:{port}/v1/models',
                                        headers={'Authorization': 'Bearer ' + key})
        try:
            with opener.open(request, timeout=3) as response:
                data = json.load(response)
            if any(item['id'] == 'Qwen3-8B' for item in data.get('data', [])):
                return
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        time.sleep(2)
    raise TimeoutError('Actor startup timed out; inspect actor-server.log')


def run_task(work, task, raw_logs, mode):
    if not raw_logs:
        raise ValueError('Add --native-raw-logs to permit native synthetic task transcripts.')
    gpu_check()
    data = json.loads((work / 'assets.json').read_text())
    if data['vllm_version'] != VLLM_VERSION:
        raise ValueError('Prepared server version differs; rerun prepare.')
    # Fail on an unknown task before loading the actor.
    execute([python_at(work, 'gate'), '-c',
        "import sys; from agentdojo.task_suite.load_suites import get_suite; "
        "s=get_suite('v1.2.2','workspace'); assert sys.argv[1] in s.user_tasks, 'Unknown task ID'", task])
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    config = json.loads((ROOT / 'configs/blackbox/wall_gatekeeper.json').read_text())
    config['mode'] = mode
    config['actor'].update(model_revision=data['actor_revision'], local_model_path=data['actor_path'],
        template_provenance='Qwen/Qwen3-8B@' + data['actor_revision'], server_version=VLLM_VERSION,
        quantization=data['quantization'], base_url=f'http://127.0.0.1:{port}/v1', max_output_tokens=1024)
    config['gatekeeper'].update(cache_dir=str(work / 'hf'), timeout_seconds=120.0, load_timeout_seconds=600.0)
    config['agentdojo']['user_task_ids'] = [task]
    for field in ('policy_path', 'metadata_path'):
        config['wall'][field] = str((ROOT / 'configs/blackbox' / config['wall'][field]).resolve())
    config['audit']['output_directory'] = str(work / 'runs')
    config_path = work / 'experiment.local.json'
    config_path.write_text(json.dumps(config, indent=2))
    env = environment(work, True)
    key = secrets.token_urlsafe(32)
    env.update(BLACKBOX_ACTOR_API_KEY=key, VLLM_API_KEY=key)
    execute([python_at(work, 'gate'), '-m', 'blackbox.cli', 'preflight', '--config', config_path], env=env)
    print('Starting local actor; startup log:', work / 'actor-server.log', flush=True)
    with (work / 'actor-server.log').open('w') as log:
        process = subprocess.Popen(server_command(work, data, port), cwd=ROOT, env=env,
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            wait_ready(process, port, key)
            execute([python_at(work, 'gate'), '-m', 'integrations.agentdojo.runner',
                     '--config', config_path, '--native-raw-logs'], env=env)
        finally:
            # Own process group only; include worker processes if server crashes.
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            except ProcessLookupError:
                process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['tests', 'prepare', 'list-tasks', 'run', '_assets'])
    parser.add_argument('--work-dir', type=Path, default=Path('/content/blackbox-colab'))
    parser.add_argument('--actor-revision', help='Exact Qwen commit; first prepare otherwise resolves and records it')
    parser.add_argument('--task', help='Exactly one real user-task ID from list-tasks')
    parser.add_argument('--mode', choices=['wall_gatekeeper', 'wall_only', 'wall_rules', 'unprotected'], default='wall_gatekeeper')
    parser.add_argument('--native-raw-logs', action='store_true')
    args = parser.parse_args()
    if platform.system() != 'Linux' or not (3, 10) <= sys.version_info[:2] <= (3, 12):
        parser.error('Use Linux/Colab with Python 3.10-3.12 for this proposed profile.')
    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    if args.command == 'tests':
        install(work, False)
        tests(work)
    elif args.command == 'prepare':
        gpu_check()
        if shutil.disk_usage(work).free < 45 * 1024**3:
            raise RuntimeError('Allow at least 45 GiB free disk for initial environments, packages and model assets.')
        install(work, True)
        tests(work)
        cmd = [python_at(work, 'gate'), SCRIPT, '_assets', '--work-dir', work]
        if args.actor_revision:
            cmd += ['--actor-revision', args.actor_revision]
        execute(cmd, env=environment(work, False))
        # Verify all Laya dependencies can load in a fresh offline process.
        execute([python_at(work, 'gate'), '-c',
            "import json; from laya import Agent; "
            "m=json.load(open('gatekeeper/model_manifest.json'))['baseline']; "
            "Agent(model_id_or_path=m['checkpoint'], revision=m['revision'], "
            "device='cpu', fast=False, compile=False, backend='eager')"], env=environment(work, True))
        print('Prepared assets. Use list-tasks, then run --task ID --native-raw-logs.', flush=True)
    elif args.command == '_assets':
        assets(work, args.actor_revision)
    elif args.command == 'list-tasks':
        list_tasks(work)
    else:
        if not args.task:
            parser.error('run requires --task with one selected ID')
        run_task(work, args.task, args.native_raw_logs, args.mode)


if __name__ == '__main__':
    main()
