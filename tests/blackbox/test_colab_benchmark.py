"""Pilot orchestration/report tests; no models, endpoints, installs or benchmarks."""
import io
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts import benchmark_colab as bench


def lines(path, values):
    path.write_text(''.join(json.dumps(value) + '\n' for value in values), encoding='utf-8')


def test_report_keeps_failures_interruption_and_unstarted_tasks(tmp_path):
    rows = [dict(task_id='user_task_0', official_utility=True, terminal='completed', seconds=20,
        episode_id='e0', executed_dispatches=1, evaluated_action_attempts=1, ask_decisions=0),
        dict(task_id='user_task_1', official_utility=False, terminal='infrastructure_error', seconds=30,
        episode_id='e1', executed_dispatches=0, evaluated_action_attempts=0, ask_decisions=0)]
    lines(tmp_path / 'scores.jsonl', rows)
    lines(tmp_path / 'events.jsonl', [dict(event='gate_decision', episode_id='e0',
        backend='existing_laya', raw_recommendation='ALLOW', error_kind=None, reason_code='TASK_AUTHORIZED',
        decision='ALLOW', elapsed_seconds=0.25)])
    bench.write_json(tmp_path / 'progress.json', {'active_task': 'user_task_2'})
    result = bench.report(tmp_path, bench.DEFAULT_TASKS, 'deadline_reached', 900, 900)
    assert result['scored_tasks'] == 2 and result['official_task_successes'] == 1
    assert result['official_utility_rate_on_scored_tasks'] == .5
    assert result['selected_panel_success_fraction'] == .2
    assert result['laya_predictions_returned'] == 1
    assert result['mean_laya_evaluation_seconds'] == 0.25
    assert result['observed_gate_decision_counts'] == {'ALLOW': 1}
    assert result['tasks'][2]['terminal'] == 'interrupted'
    assert result['tasks'][2]['executed_dispatches'] is None
    assert result['tasks'][3]['terminal'] == 'not_started'
    assert result['gatekeeper_accuracy'] is None and result['attack_success_rate'] is None
    assert 'Infrastructure errors occurred' in (tmp_path / 'REPORT.md').read_text()


def test_report_does_not_claim_effectiveness_without_laya(tmp_path):
    result = bench.report(tmp_path, bench.DEFAULT_TASKS, 'setup_error', 3, 900)
    assert result['official_utility_rate_on_scored_tasks'] is None
    assert result['scored_tasks'] == 0 and result['unscored_tasks'] == 5
    assert 'does not demonstrate gatekeeper effectiveness' in (tmp_path / 'REPORT.md').read_text()


def test_errors_expose_status_not_response_body_or_credentials():
    cause = RuntimeError('private prompt / token')
    cause.response = SimpleNamespace(status_code=400)
    failure = RuntimeError('secret')
    failure.__cause__ = cause
    assert bench.error_details(failure) == [dict(type='RuntimeError'), dict(type='RuntimeError', http_status=400)]


def test_interrupted_last_jsonl_write_is_not_a_fabricated_score(tmp_path):
    p = tmp_path / 'scores.jsonl'
    p.write_text('{"official_utility": false}\n{"task_id":')
    assert bench.read_lines(p) == [{'official_utility': False}]
    p.write_text('broken\n{}\n')
    with pytest.raises(json.JSONDecodeError):
        bench.read_lines(p)


@pytest.mark.parametrize('valid', [True, False])
def test_probe_requires_actual_structured_call(monkeypatch, valid):
    choice = {'finish_reason': 'tool_calls' if valid else 'length', 'message': {'tool_calls': [
        {'function': {'name': 'benchmark_probe', 'arguments': '{"value":"ready"}'}}]}}
    monkeypatch.setattr(bench.urllib.request, 'build_opener', lambda *a:
        SimpleNamespace(open=lambda *a, **k: io.BytesIO(json.dumps({'choices': [choice]}).encode())))
    if valid:
        assert bench.probe_actor(8000, 'test-key', 1)['tools_executed'] == 0
    else:
        with pytest.raises(RuntimeError, match='ACTOR_TOOL_PROBE_FAILED'):
            bench.probe_actor(8000, 'test-key', 1)


def test_trial_deadline_stops_both_process_groups_and_exports_partial_report(tmp_path, monkeypatch):
    bench.write_json(tmp_path / 'assets.json', {'actor_path': '/models/qwen', 'actor_revision': 'a' * 40,
        'vllm_version': bench.helper.VLLM_VERSION, 'quantization': 'bitsandbytes-4bit-inflight'})
    monkeypatch.setattr(bench.helper, 'require_git', lambda: None)
    monkeypatch.setattr(bench.helper, 'gpu_check', lambda: None)
    monkeypatch.setattr(bench.helper, 'execute', lambda *a, **k: None)
    monkeypatch.setattr(bench.helper, 'wait_ready', lambda *a, **k: None)
    monkeypatch.setattr(bench, 'probe_actor', lambda *a, **k: {'status': 'passed'})
    children = []
    def popen(*args, **kwargs):
        def wait(**kwargs):
            raise subprocess.TimeoutExpired('worker', 900)
        process = SimpleNamespace(wait=wait)
        children.append(process)
        return process
    monkeypatch.setattr(bench.subprocess, 'Popen', popen)
    stopped = []
    monkeypatch.setattr(bench.helper, 'stop_process', stopped.append)
    assert bench.benchmark(tmp_path, bench.DEFAULT_TASKS, 900, 150) == 2
    assert stopped == list(reversed(children))
    latest = json.loads((tmp_path / 'latest-benchmark.json').read_text())
    assert Path(latest['archive']).is_file()
    report = json.loads((Path(latest['directory']) / 'summary.json').read_text())
    assert report['status'] == 'deadline_reached' and report['scored_tasks'] == 0


def test_config_keeps_original_laya_and_policy(tmp_path):
    from blackbox.config import Config
    config = bench.helper.make_config(tmp_path, {'actor_path': '/models/qwen', 'actor_revision': 'a' * 40,
        'quantization': 'bitsandbytes-4bit-inflight'}, bench.DEFAULT_TASKS, 8000)
    model = Config.model_validate(config)
    assert model.mode == 'wall_gatekeeper' and model.gatekeeper.profile == 'original_single'
    assert model.agentdojo.user_task_ids == bench.DEFAULT_TASKS
    assert model.wall.policy_path.endswith('workspace_example.json')
    assert 'transformers==4.57.6' in bench.helper.ACTOR_PACKAGES


def test_worker_reuses_pipeline_and_keeps_native_failures(tmp_path, monkeypatch):
    from contextlib import nullcontext
    import agentdojo.benchmark
    import agentdojo.logging
    import agentdojo.task_suite.load_suites
    import blackbox.factory
    import blackbox.manifest
    import integrations.agentdojo.runner
    config = bench.helper.make_config(tmp_path, {'actor_path': '/models/qwen',
        'actor_revision': 'a' * 40, 'quantization': 'bitsandbytes-4bit-inflight'},
        ['user_task_0', 'user_task_1'], 8000)
    config_path = tmp_path / 'config.json'
    bench.write_json(config_path, config)
    backend = SimpleNamespace(error=None, error_kind=None)
    gate = SimpleNamespace(initialize=lambda: None,
                          gate=SimpleNamespace(initialize=lambda: None, backend=backend))
    pipeline = SimpleNamespace(gate=gate, last_episode=None)
    constructions = []
    def build(*args):
        constructions.append(args)
        return nullcontext(pipeline)
    monkeypatch.setattr(blackbox.factory, 'build_agentdojo_pipeline', build)
    monkeypatch.setattr(integrations.agentdojo.runner, 'verify_distribution', lambda c: None)
    monkeypatch.setattr(blackbox.manifest, 'create_manifest', lambda *a:
        SimpleNamespace(model_dump_json=lambda **k: '{}'))
    suite = SimpleNamespace(name='workspace', user_tasks={'user_task_0': None, 'user_task_1': None},
                            get_user_task_by_id=lambda name: SimpleNamespace(ID=name))
    monkeypatch.setattr(agentdojo.task_suite.load_suites, 'get_suite', lambda *a: suite)
    monkeypatch.setattr(agentdojo.logging, 'OutputLogger', lambda *a: nullcontext())
    def native_run(suite, current_pipeline, task, *args):
        assert current_pipeline is pipeline
        if task.ID == 'user_task_0':
            raise OSError('synthetic native failure')
        pipeline.last_episode = SimpleNamespace(episode_id='e1', terminal='completed',
            executed=1, calls=1, asks=0, error_context=None)
        return True, True
    monkeypatch.setattr(agentdojo.benchmark, 'run_task_without_injection_tasks', native_run)
    bench.worker(config_path, tmp_path)
    rows = bench.read_lines(tmp_path / 'scores.jsonl')
    assert len(constructions) == 1 and len(rows) == 2
    assert rows[0]['official_utility'] is None and rows[0]['terminal'] == 'native_infrastructure_failure'
    assert rows[0]['error_chain'] == [{'type': 'OSError'}]
    assert rows[1]['official_utility'] is True and rows[1]['executed_dispatches'] == 1
    assert all(row['attack_success'] is None for row in rows)
