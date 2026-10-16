"""Bounded clean AgentDojo pilot: Qwen actor + original Laya, with report export."""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import colab_blackbox as helper

DEFAULT_TASKS = ['user_task_0', 'user_task_1', 'user_task_2', 'user_task_3', 'user_task_10']


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)


def error_details(exc):
    """Diagnostic classes/status only: no response bodies, credentials or prompts."""
    result, seen = [], set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        item = {'type': type(exc).__name__}
        status = getattr(getattr(exc, 'response', None), 'status_code', None)
        if status is None and isinstance(getattr(exc, 'code', None), int):
            status = exc.code
        if status is not None:
            item['http_status'] = status
        result.append(item)
        nested = getattr(exc, 'reason', None)
        exc = exc.__cause__ or exc.__context__ or (nested if isinstance(nested, Exception) else None)
    return result


def read_lines(path):
    if not path.exists():
        return []
    lines = path.read_text(encoding='utf-8').splitlines()
    records = []
    for i, line in enumerate(lines):
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            if i != len(lines) - 1:
                raise
            # A hard deadline may interrupt the last write; never invent a score.
    return records


def probe_actor(port, key, timeout):
    body = {'model': 'Qwen3-8B', 'messages': [
        {'role': 'user', 'content': 'Call benchmark_probe with value ready. Do not answer in text.'}],
        'tools': [{'type': 'function', 'function': {'name': 'benchmark_probe',
            'description': 'A harmless diagnostic; no tool will execute.',
            'parameters': {'type': 'object', 'properties': {'value': {'type': 'string'}},
                           'required': ['value'], 'additionalProperties': False}}}],
        'tool_choice': 'auto', 'max_tokens': 128, 'temperature': 0.0,
        'chat_template_kwargs': {'enable_thinking': False}}
    request = urllib.request.Request(f'http://127.0.0.1:{port}/v1/chat/completions',
        data=json.dumps(body).encode(), headers={'Content-Type': 'application/json',
                                                'Authorization': 'Bearer ' + key})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    started = time.monotonic()
    with opener.open(request, timeout=timeout) as response:
        choice = json.load(response)['choices'][0]
    calls = choice.get('message', {}).get('tool_calls') or []
    if choice.get('finish_reason') not in ('stop', 'tool_calls') or len(calls) != 1:
        raise RuntimeError('ACTOR_TOOL_PROBE_FAILED')
    function = calls[0]['function']
    if function['name'] != 'benchmark_probe' or json.loads(function['arguments']) != {'value': 'ready'}:
        raise RuntimeError('ACTOR_TOOL_PROBE_FAILED')
    return {'status': 'passed', 'seconds': time.monotonic() - started,
            'tools_executed': 0, 'counts_toward_benchmark': False}


def worker(config_path, output):
    # Imports/models are confined to the explicitly launched gate subprocess.
    from agentdojo.benchmark import run_task_without_injection_tasks
    from agentdojo.logging import OutputLogger
    from agentdojo.task_suite.load_suites import get_suite
    from blackbox.config import load_config
    from blackbox.contracts import Dependencies
    from blackbox.factory import build_agentdojo_pipeline
    from blackbox.manifest import create_manifest
    from integrations.agentdojo.runner import verify_distribution
    config = load_config(config_path)
    config.require_selection()
    verify_distribution(config)
    suite = get_suite(config.agentdojo.benchmark_version, config.agentdojo.suite)
    if set(config.agentdojo.user_task_ids) - set(suite.user_tasks):
        raise ValueError('Unknown selected task ID')
    (output / 'manifest.json').write_text(
        create_manifest(config, output.name).model_dump_json(indent=2), encoding='utf-8')
    with build_agentdojo_pipeline(config, Dependencies(run_id=output.name)) as pipeline:
        write_json(output / 'progress.json', {'phase': 'laya_warmup', 'active_task': None})
        start = time.monotonic()
        pipeline.gate.initialize()
        pipeline.gate.gate.initialize()
        backend = pipeline.gate.gate.backend
        write_json(output / 'laya_warmup.json', {'seconds': time.monotonic() - start,
            'status': 'failed' if backend.error else 'passed',
            'error_kind': backend.error_kind, 'counts_toward_benchmark': False})
        if backend.error:
            raise RuntimeError('LAYA_WARMUP_FAILED')
        with OutputLogger(str(output / 'native')):
            for task_id in config.agentdojo.user_task_ids:
                task = suite.get_user_task_by_id(task_id)
                pipeline.metadata = {'suite': suite.name, 'task_id': task_id, 'injection_task_id': None}
                pipeline.last_episode = None
                write_json(output / 'progress.json', {'phase': 'evaluating', 'active_task': task_id})
                start = time.monotonic()
                utility, security, failure = None, None, []
                try:
                    utility, security = run_task_without_injection_tasks(
                        suite, pipeline, task, output / 'native', False, config.agentdojo.benchmark_version)
                except Exception as exc:
                    failure = error_details(exc)
                episode = pipeline.last_episode
                if episode and episode.error_context:
                    failure = error_details(episode.error_context)
                row = {'task_id': task_id, 'official_utility': utility,
                    'official_security_field': security, 'attack_success': None,
                    'episode_id': episode.episode_id if episode else None,
                    'terminal': 'native_infrastructure_failure' if utility is None else (
                        episode.terminal if episode else 'native_infrastructure_failure'),
                    'seconds': round(time.monotonic() - start, 3),
                    'executed_dispatches': episode.executed if episode else 0,
                    'evaluated_action_attempts': episode.calls if episode else 0,
                    'ask_decisions': episode.asks if episode else 0,
                    'error_chain': failure}
                with (output / 'scores.jsonl').open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps(row) + '\n')
                    stream.flush()
                write_json(output / 'progress.json', {'phase': 'between_tasks', 'active_task': None})
                print(f"{task_id}: utility={utility}, terminal={row['terminal']}, "
                      f"tools={row['executed_dispatches']}, seconds={row['seconds']}", flush=True)
    write_json(output / 'progress.json', {'phase': 'finished', 'active_task': None})


def report(output, tasks, status, elapsed, budget):
    scores = {row['task_id']: row for row in read_lines(output / 'scores.jsonl')}
    events = read_lines(output / 'events.jsonl')
    progress_path = output / 'progress.json'
    progress = json.loads(progress_path.read_text()) if progress_path.exists() else {}
    active = progress.get('active_task')
    rows = []
    for task in tasks:
        row = dict(scores.get(task) or {'task_id': task, 'official_utility': None,
            'terminal': ('interrupted' if task == active else 'not_started'), 'seconds': None,
            'executed_dispatches': None if task == active else 0,
            'evaluated_action_attempts': None if task == active else 0,
            'ask_decisions': None if task == active else 0,
            'error_chain': []})
        episode_events = [event for event in events if event['episode_id'] == row.get('episode_id')]
        gates = [event for event in episode_events if event['event'] == 'gate_decision'
                 and event.get('backend') == 'existing_laya']
        row['laya_evaluations'] = len(gates)
        row['laya_predictions_returned'] = sum(event.get('raw_recommendation') is not None
                                             and not event.get('error_kind') for event in gates)
        rows.append(row)
    scored = sum(isinstance(row['official_utility'], bool) for row in rows)
    successes = sum(row['official_utility'] is True for row in rows)
    predictions = sum(row['laya_predictions_returned'] for row in rows)
    gate_events = [event for event in events if event['event'] == 'gate_decision'
                   and event.get('backend') == 'existing_laya']
    gate_errors = dict(Counter(event['error_kind'] for event in gate_events if event.get('error_kind')))
    if status == 'completed' and gate_errors:
        status = 'completed_with_gate_errors'
    gate_times = [event['elapsed_seconds'] for event in gate_events if 'elapsed_seconds' in event]
    actor_times = [event['elapsed_seconds'] for event in events
                   if event['event'] == 'actor_response' and 'elapsed_seconds' in event]
    summary = {'label': 'Clean workspace pilot: Qwen3-8B + original Laya + reference wall',
        'status': status, 'seconds': round(elapsed, 2), 'budget_seconds': budget,
        'selected_tasks': len(tasks), 'scored_tasks': scored, 'official_task_successes': successes,
        'official_utility_rate_on_scored_tasks': successes / scored if scored else None,
        'selected_panel_success_fraction': successes / len(tasks),
        'unscored_tasks': len(tasks) - scored, 'terminal_counts': dict(Counter(r['terminal'] for r in rows)),
        'laya_predictions_returned': predictions,
        'laya_raw_predictions_returned': sum(event.get('raw_recommendation') is not None for event in gate_events),
        'gate_error_counts': gate_errors,
        'observed_gate_decision_counts': dict(Counter(event.get('decision') for event in gate_events)),
        'mean_laya_evaluation_seconds': sum(gate_times) / len(gate_times) if gate_times else None,
        'mean_actor_response_seconds': sum(actor_times) / len(actor_times) if actor_times else None,
        'gate_reason_counts': dict(Counter(event.get('reason_code') for event in events
                                          if event['event'] == 'gate_decision')),
        'attack_success_rate': None, 'gatekeeper_accuracy': None,
        'limitations': ['Explicitly selected clean workspace tasks; see config.json for the task IDs.',
            'Clean tasks only: no prompt-injection robustness claim.',
            'Native task utility is not gatekeeper classification accuracy.',
            'Pending approvals, failures and unscored tasks are retained.',
            '4-bit actor profile; original uncalibrated Laya and reference policy unchanged.'],
        'tasks': rows}
    write_json(output / 'summary.json', summary)
    columns = ['task_id', 'official_utility', 'terminal', 'seconds', 'executed_dispatches',
               'evaluated_action_attempts', 'ask_decisions', 'laya_evaluations', 'laya_predictions_returned']
    with (output / 'summary.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    rate = f'{100 * successes / scored:.1f}%' if scored else 'not available'
    lines = ['# Qwen + original Laya: clean AgentDojo pilot', '',
        f'- Execution status: **{status}**', f'- Elapsed: {elapsed:.1f}s; time budget: {budget}s (setup/download excluded).',
        f'- Official task successes: **{successes}/{scored} scored ({rate})**; {len(tasks)} selected.',
        f'- Unscored tasks: {len(tasks) - scored}. They are not counted as successes.',
        f'- Usable Laya predictions accepted during task episodes: **{predictions}**.',
        f"- Raw Laya predictions returned: {summary['laya_raw_predictions_returned']}; gate errors: {gate_errors}.",
        f"- Observed gate decisions: {summary['observed_gate_decision_counts']}.",
        f"- Mean Laya evaluation seconds: {summary['mean_laya_evaluation_seconds']} (null = unavailable).", '',
        '| Task | Official utility | Terminal | Seconds | Tool executions | Usable Laya predictions |',
        '|---|---|---|---:|---:|---:|']
    for row in rows:
        utility = 'unscored' if row['official_utility'] is None else str(row['official_utility'])
        lines.append(f"| {row['task_id']} | {utility} | {row['terminal']} | "
                     f"{row['seconds']} | {row['executed_dispatches']} | {row['laya_predictions_returned']} |")
    lines += ['', '## Interpretation', '', *['- ' + item for item in summary['limitations']]]
    if any('infrastructure' in row['terminal'] for row in rows):
        lines += ['', '**Infrastructure errors occurred. Process completion does not mean every task ran successfully.**']
    if not predictions:
        lines += ['', '**No usable task-level Laya predictions were accepted. This does not demonstrate gatekeeper effectiveness.**']
    lines += ['', '## Evidence', '',
        'See manifest.json/config.json for exact model and policy identity; summary.json for error chains;',
        'events.jsonl/native/ for task traces; actor-server.log and worker.log for failures;',
        'actor-probe.json and laya_warmup.json for prechecks. Warmups are excluded from task scores.']
    (output / 'REPORT.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return summary


def benchmark(work, tasks, seconds, task_seconds, injection_panel=None):
    panel = None
    if injection_panel is not None:
        from scripts.injection_pilot import load_panel
        panel = load_panel(injection_panel)
        tasks = [case['user_task_id'] for case in panel['cases']]
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:8]
    output = work / 'benchmarks' / stamp
    output.mkdir(parents=True)
    if panel:
        write_json(output / 'injection-panel.json', panel)
    started = time.monotonic()
    deadline = started + seconds
    status = 'setup_error'
    server = child = None
    def remaining():
        value = deadline - time.monotonic()
        if value <= 0:
            raise TimeoutError('BENCHMARK_DEADLINE')
        return value
    try:
        helper.require_git()
        write_json(output / 'hardware.json', helper.gpu_check())
        data = json.loads((work / 'assets.json').read_text())
        if data['vllm_version'] != helper.VLLM_VERSION:
            raise ValueError('Prepared vLLM differs; run prepare.')
        env = helper.environment(work, True)
        key = secrets.token_urlsafe(32)
        env.update(BLACKBOX_ACTOR_API_KEY=key, VLLM_API_KEY=key)
        # Record exact installed server packages and fail before GPU loading on
        # the Transformers 5 incompatibility actually observed in the notebook.
        helper.execute([helper.python_at(work, 'actor'), '-c',
            "from importlib.metadata import version; "
            "assert version('transformers') == '4.57.6', 'Run colab_blackbox.py repair-actor'; "
            "assert version('vllm') == '0.11.0', 'Run colab_blackbox.py repair-actor'"], timeout=remaining())
        for name in ('actor', 'gate'):
            with (output / (name + '-freeze.txt')).open('w') as stream:
                helper.execute([helper.python_at(work, name), '-m', 'pip', 'freeze'],
                               stdout=stream, timeout=remaining())
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        config = helper.make_config(work, data, tasks, port)
        config['actor'].update(timeout_seconds=float(task_seconds), max_retries=0, max_output_tokens=512,
                               temperature=0.0)
        config['runtime'] = {'max_episode_seconds': float(task_seconds), 'max_actor_turns': 6,
                             'max_tool_calls': 12}
        config['gatekeeper'].update(timeout_seconds=60.0, load_timeout_seconds=180.0)
        config['audit'].update(output_directory=str(output.parent), record_raw_content=True)
        config_path = output / 'config.json'
        write_json(config_path, config)
        helper.execute([helper.python_at(work, 'gate'), '-m', 'blackbox.cli', 'preflight',
                        '--config', config_path], env=env, timeout=remaining())
        # Native IDs are checked before loading the GPU model.
        helper.execute([helper.python_at(work, 'gate'), '-c',
            "import sys; from agentdojo.task_suite.load_suites import get_suite; "
            "s=get_suite('v1.2.2','workspace'); assert set(sys.argv[1:]) <= set(s.user_tasks), 'Unknown task ID'",
            *tasks], env=env, timeout=remaining())
        worker_command = [str(helper.python_at(work, 'gate')), str(Path(__file__).resolve()),
                          '_worker', '--config', str(config_path), '--output', str(output)]
        if panel:
            injection_script = ROOT / 'scripts/injection_pilot.py'
            panel_args = ['--panel', str(output / 'injection-panel.json')]
            helper.execute([helper.python_at(work, 'gate'), injection_script, '_validate', *panel_args],
                           env=env, timeout=remaining())
            worker_command = [str(helper.python_at(work, 'gate')), str(injection_script),
                '_worker', '--config', str(config_path), '--output', str(output), *panel_args]
        print('Report directory:', output, flush=True)
        print('Loading Qwen; startup progress is in actor-server.log. Please leave this cell running.', flush=True)
        with (output / 'actor-server.log').open('w') as log:
            server = subprocess.Popen(helper.server_command(work, data, port), cwd=ROOT, env=env,
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            helper.wait_ready(server, port, key, timeout=min(360, remaining()))
            write_json(output / 'actor-probe.json', probe_actor(port, key, min(120, remaining())))
            print('Actor tool-call probe passed. Starting Laya warmup and selected tasks.', flush=True)
            with (output / 'worker.log').open('w') as worker_log:
                child = subprocess.Popen(worker_command, cwd=ROOT, env=env,
                    stdout=worker_log, stderr=subprocess.STDOUT, start_new_session=True)
                code = child.wait(timeout=remaining())
                status = 'completed' if code == 0 else 'worker_error'
    except (TimeoutError, subprocess.TimeoutExpired):
        status = 'deadline_reached'
    except Exception as exc:
        write_json(output / 'failure.json', {'error_chain': error_details(exc)})
        print('Benchmark setup/execution failed:', type(exc).__name__, flush=True)
    except KeyboardInterrupt:
        status = 'interrupted_by_user'
    finally:
        for process in (child, server):
            if process is not None:
                helper.stop_process(process)
        if status == 'completed' and any('infrastructure' in row['terminal']
                for row in read_lines(output / 'scores.jsonl')):
            status = 'completed_with_infrastructure_errors'
        if panel:
            from scripts.injection_pilot import report as injection_report
            summary = injection_report(output, panel, status, time.monotonic() - started, seconds)
        else:
            summary = report(output, tasks, status, time.monotonic() - started, seconds)
        status = summary['status']
        archive = shutil.make_archive(str(output), 'zip', root_dir=output)
        write_json(work / 'latest-benchmark.json', {'directory': str(output), 'archive': archive})
        print((output / 'REPORT.md').read_text(encoding='utf-8'), flush=True)
        print('Download:', archive, flush=True)
    if status in ('completed_with_infrastructure_errors', 'completed_with_gate_errors'):
        return 1
    if status != 'completed':
        return 2
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['run', '_worker'])
    parser.add_argument('--work-dir', type=Path, default=Path('/content/blackbox-colab'))
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument('--tasks', nargs='+')
    selection.add_argument('--injection-panel', type=Path,
                           help='Run clean/injected comparisons in all three modes using explicit fixed payloads')
    parser.add_argument('--seconds', type=int, default=900, help='Total trial deadline, including server startup')
    parser.add_argument('--task-seconds', type=int, default=150)
    parser.add_argument('--native-raw-logs', action='store_true')
    parser.add_argument('--config', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    args.tasks = args.tasks or DEFAULT_TASKS
    if args.command == '_worker':
        worker(args.config, args.output)
        return 0
    if platform.system() != 'Linux' or not (3, 10) <= sys.version_info[:2] <= (3, 12):
        parser.error('Use /content/py312/bin/python after the Python 3.12 setup in COLAB_BENCHMARK.md.')
    if not args.native_raw_logs:
        parser.error('Add --native-raw-logs for native synthetic transcripts.')
    if args.seconds < 30 or args.task_seconds < 1 or len(set(args.tasks)) != len(args.tasks):
        parser.error('Budget must be >=30s, task budget positive, and task IDs unique.')
    return benchmark(args.work_dir.resolve(), args.tasks, args.seconds, args.task_seconds, args.injection_panel)


if __name__ == '__main__':
    raise SystemExit(main())
