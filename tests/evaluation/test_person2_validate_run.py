"""Person 2 run validation against real run folders from a local fake endpoint; never performance evidence.

Two episodes (clean user_task_0 and its calendar_email attack) run through the real experiment runtime and
OpenAI-compatible actor, talking to an in-process fake server on localhost. No model or external service.
"""
import importlib.util
import json
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from experiment.aggregate import aggregate
from experiment.runtime import execute
from experiment.scheduler import schedule
from experiment.services import Services
from experiment.spec import load
from experiment.store import compatible, create_run

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / 'configs/experiments/pilot-panel/unprotected.json'
SCRIPT = ROOT / 'scripts' / 'person2_validate_run.py'
module_spec = importlib.util.spec_from_file_location('person2_validate_run', SCRIPT)
validate = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(validate)


class FakeModel(BaseHTTPRequestHandler):
    """Reads the calendar without a date (so the injected event is returned), then answers."""

    def log_message(self, *args):
        pass

    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if request['messages'][-1]['role'] == 'tool':
            message = {'role': 'assistant', 'content': 'Done.'}
        else:
            message = {'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'call_1', 'type': 'function',
                       'function': {'name': 'search_calendar_events', 'arguments': '{"query": "Networking event"}'}}]}
        body = json.dumps({'id': 'x', 'object': 'chat.completion', 'created': 0, 'model': 'Qwen2.5-7B-Instruct',
                           'choices': [{'index': 0, 'finish_reason': 'stop', 'message': message}],
                           'usage': {'prompt_tokens': 10, 'completion_tokens': 2, 'total_tokens': 12}}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(scope='module')
def finished_run(tmp_path_factory):
    server = ThreadingHTTPServer(('127.0.0.1', 0), FakeModel)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    folder = tmp_path_factory.mktemp('person2')
    config = json.loads(PANEL.read_text(encoding='utf-8'))
    config['clean_tasks'] = ['user_task_0']
    config['attacks'] = [a for a in config['attacks'] if a['id'] == 'calendar_email']
    (profile,) = config['actors'].values()
    profile['settings']['base_url'] = f'http://127.0.0.1:{server.server_port}/v1'
    config_path = folder / 'two-episodes.json'
    config_path.write_text(json.dumps(config))
    patch = pytest.MonkeyPatch()
    patch.setenv('BLACKBOX_ACTOR_API_KEY', 'local-test')
    try:
        spec = load(config_path)
        directory = create_run(spec, folder / 'runs')
        services = Services(spec)
        try:
            schedule(spec, compatible(directory, spec), directory,
                     lambda *a: execute(spec, services, directory, *a))
        finally:
            services.close()
        aggregate(directory)
    finally:
        patch.undo()
        server.shutdown()
    return directory, config_path


def statuses(checks):
    return {item['check']: item['status'] for item in checks.items}


@pytest.mark.parametrize('config', [PANEL, ROOT / 'configs/experiments/panel-15/unprotected.json',
                                    ROOT / 'configs/experiments/hard-tasks/unprotected.json'])
def test_preflight_passes_for_the_committed_panels(config, monkeypatch):
    monkeypatch.setenv('BLACKBOX_ACTOR_API_KEY', 'local-test')
    checks = validate.preflight(config)
    assert checks.overall == 'PASS', checks.items


def test_preflight_rejects_changed_actor_extra_mode_and_drifted_attack(tmp_path, monkeypatch):
    monkeypatch.setenv('BLACKBOX_ACTOR_API_KEY', 'local-test')
    config = json.loads(PANEL.read_text(encoding='utf-8'))
    config['modes'] = ['unprotected', 'wall_only']
    next(iter(config['actors'].values()))['settings']['temperature'] = 0.7
    config['attacks'][0]['payloads'] = {'calendar_networking_event_injection_email': 'BB_INJECT_CAL_EMAIL_01 changed'}
    path = tmp_path / 'changed.json'
    path.write_text(json.dumps(config))
    result = statuses(validate.preflight(path))
    assert result['Only the unprotected mode is selected'] == 'FAIL'
    assert result['Actor settings equal the frozen baseline'] == 'FAIL'
    assert result['Attacks are identical to the team attack panels'] == 'FAIL'


def test_check_run_passes_on_a_complete_run(finished_run):
    directory, config = finished_run
    checks, rows = validate.check_run(directory, config)
    assert checks.overall == 'PASS', checks.items
    assert [(r['task'], r['attack']) for r in rows] == [('user_task_0', None), ('user_task_0', 'calendar_email')]
    assert rows[1]['attack_exposed'] is True and rows[1]['attack_success'] is not None


def test_check_run_detects_tampered_and_missing_results(finished_run, tmp_path):
    directory, config = finished_run
    copy = tmp_path / directory.name
    shutil.copytree(directory, copy)
    results = sorted(copy.glob('episodes/*/*/result.json'))
    conversation = results[0].parent / 'conversation.json'
    conversation.write_text(conversation.read_text(encoding='utf-8') + ' ', encoding='utf-8')
    results[1].unlink()
    result = statuses(validate.check_run(copy, config)[0])
    assert result['Result files are intact and match their planned job'] == 'FAIL'
    assert result['Every planned episode has a finished attempt'] == 'FAIL'


def test_check_run_detects_wrong_model_and_changed_config(finished_run, tmp_path):
    directory, config = finished_run
    changed = json.loads(Path(config).read_text(encoding='utf-8'))
    next(iter(changed['actors'].values()))['settings']['served_model_name'] = 'Other-Model'
    path = tmp_path / 'other.json'
    path.write_text(json.dumps(changed))
    result = statuses(validate.check_run(directory, path)[0])
    assert result['Run used the given configuration unchanged'] == 'FAIL'
    assert result['Every response came from the expected model'] == 'FAIL'


def test_check_run_refuses_to_write_inside_the_run(finished_run):
    directory, config = finished_run
    import subprocess
    import sys
    completed = subprocess.run([sys.executable, str(SCRIPT), 'check-run', '--run-dir', str(directory),
                                '--config', str(config), '--output', str(directory / 'validation.json')],
                               capture_output=True, text=True, cwd=ROOT)
    assert completed.returncode != 0 and not (directory / 'validation.json').exists()
