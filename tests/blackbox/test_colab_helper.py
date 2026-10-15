"""Exercise orchestration without installing packages or starting models."""
import json
from types import SimpleNamespace
import pytest
from scripts import colab_blackbox as helper


def test_colab_server_has_bounded_quantized_local_profile(tmp_path):
    cmd = helper.server_command(tmp_path, {'actor_path': '/models/qwen'}, 8123)
    for option, value in [('--host', '127.0.0.1'), ('--port', '8123'),
                          ('--quantization', 'bitsandbytes'), ('--dtype', 'half'),
                          ('--max-model-len', '8192'), ('--max-num-seqs', '1'),
                          ('--tool-call-parser', 'hermes')]:
        assert cmd[cmd.index(option) + 1] == value
    assert '--enforce-eager' in cmd
    assert '--trust-remote-code' not in cmd


@pytest.mark.parametrize('gpu', ['Tesla P100, 16384, 6.0', 'Small GPU, 8192, 8.0'])
def test_colab_rejects_unsuitable_gpu(monkeypatch, gpu):
    monkeypatch.setattr(helper.subprocess, 'check_output', lambda *a, **k: gpu)
    with pytest.raises(RuntimeError, match='T4-class'):
        helper.gpu_check()


def test_colab_requires_raw_log_opt_in_before_any_model_work(tmp_path, monkeypatch):
    monkeypatch.setattr(helper, 'gpu_check', lambda: pytest.fail('Unexpected GPU work'))
    with pytest.raises(ValueError, match='native-raw-logs'):
        helper.run_task(tmp_path, 'user_task_0', False, 'wall_gatekeeper')


def test_colab_cleans_up_server_on_startup_failure(tmp_path, monkeypatch):
    (tmp_path / 'assets.json').write_text(json.dumps({'actor_path': '/models/qwen',
        'actor_revision': 'a' * 40, 'vllm_version': helper.VLLM_VERSION,
        'quantization': 'bitsandbytes-4bit-inflight'}))
    monkeypatch.setattr(helper, 'gpu_check', lambda: None)
    calls = []
    monkeypatch.setattr(helper, 'execute', lambda args, **kwargs: calls.append(args))
    waited = []
    monkeypatch.setattr(helper.subprocess, 'Popen', lambda *a, **k:
                        SimpleNamespace(pid=12345, wait=lambda **kw: waited.append(kw)))
    killed = []
    monkeypatch.setattr(helper.os, 'killpg', lambda pid, sig: killed.append((pid, sig)), raising=False)
    def fail(*args):
        raise TimeoutError('synthetic startup failure')
    monkeypatch.setattr(helper, 'wait_ready', fail)
    with pytest.raises(TimeoutError):
        helper.run_task(tmp_path, 'user_task_0', True, 'wall_gatekeeper')
    assert killed and killed[0][0] == 12345 and waited
    assert not any('integrations.agentdojo.runner' in call for call in calls)
    config = json.loads((tmp_path / 'experiment.local.json').read_text())
    assert config['agentdojo']['user_task_ids'] == ['user_task_0']
    assert config['actor']['quantization'] == 'bitsandbytes-4bit-inflight'
    assert config['gatekeeper']['cache_dir'] == str(tmp_path / 'hf')
    assert 'api_key' not in config['actor']


def test_colab_online_preparation_and_offline_execution_environments(tmp_path):
    assert helper.environment(tmp_path, False)['HF_HUB_OFFLINE'] == '0'
    offline = helper.environment(tmp_path, True)
    assert offline['HF_HUB_OFFLINE'] == offline['TRANSFORMERS_OFFLINE'] == '1'
    assert offline['HF_HUB_CACHE'] == str(tmp_path / 'hf/hub')


def test_colab_missing_ensurepip_uses_isolated_bootstrap(tmp_path, monkeypatch):
    calls = []
    def fake_execute(args, **kwargs):
        calls.append((args, kwargs))
        if 'venv' in args:
            raise helper.subprocess.CalledProcessError(1, args)
    monkeypatch.setattr(helper, 'execute', fake_execute)
    helper.install(tmp_path, False)
    bootstrap = next(args for args, _ in calls if '--target' in args)
    assert bootstrap[bootstrap.index('--target') + 1] == tmp_path / 'bootstrap'
    creation, options = next((args, opts) for args, opts in calls if 'virtualenv' in args)
    assert creation[-1] == tmp_path / 'gate'
    assert options['env']['PYTHONPATH'] == str(tmp_path / 'bootstrap')
    assert not any('laya==0.3.28' in args for args, _ in calls)
