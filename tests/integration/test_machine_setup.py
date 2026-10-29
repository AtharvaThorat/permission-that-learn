"""Machine preparation remains explicit; config generation reuses experiment validation."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from grids.cli import setup as setup
from grids.runs.spec import load, plan

BASE = 'configs/experiments/smoke.json'
FIRST = 'configs/models/qwen25-7b-t4.json'
SECOND = 'configs/models/qwen35-9b-a100.json'


@pytest.mark.parametrize('parallel', [False, True])
def test_config_retains_base_and_builds_model_resource_limits(tmp_path, parallel):
    original = Path(BASE).read_bytes()
    out = tmp_path / 'spec.json'
    args = ['config', '--base', BASE, '--profile', FIRST, '--profile', SECOND,
            '--cache-dir', str(tmp_path / 'hf'), '--output', str(out), '--task', 'user_task_10',
            '--clean-only', '--mode', 'wall_gatekeeper', '--gate-max-input-tokens', '8192',
            '--gate-timeout', '180'] + (['--parallel'] if parallel else [])
    setup.main(args)
    spec = load(out)
    assert plan(spec)['job_count'] == 2
    assert spec.limits.global_episodes == (2 if parallel else 1)
    if parallel:
        assert spec.limits.pending_queue >= 2
    actors = list(spec.actors.values())
    assert (actors[0].resource_group != actors[1].resource_group) is parallel
    assert (actors[0].settings.base_url != actors[1].settings.base_url) is parallel
    assert actors[1].settings.model_id == 'Qwen/Qwen3.5-9B'
    assert actors[0].settings.temperature == next(iter(load(BASE).actors.values())).settings.temperature
    assert spec.gatekeeper.max_input_tokens == 8192
    assert Path(BASE).read_bytes() == original
    saved = out.read_bytes()
    with pytest.raises(FileExistsError):
        setup.main(args)
    assert out.read_bytes() == saved


def test_invalid_selection_does_not_publish_config(tmp_path):
    out = tmp_path / 'bad.json'
    with pytest.raises(ValueError, match='Unknown native user task'):
        setup.main(['config', '--base', BASE, '--profile', FIRST, '--cache-dir', str(tmp_path),
                    '--output', str(out), '--task', 'not_a_task', '--clean-only'])
    assert not out.exists()


def test_install_dry_run_has_no_environment_or_process_side_effects(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(setup.subprocess, 'run', lambda *a, **kw: pytest.fail('Executed during dry run'))
    target = tmp_path / 'envs'
    setup.main(['install', '--work-dir', str(target), '--dry-run'])
    commands = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(commands) == 6 and not target.exists()
    requirement = next(part for c in commands for part in c if part.endswith('environments/laya.txt') or part.endswith('environments\\laya.txt'))
    assert 'laya==0.3.28' in Path(requirement).read_text()
    assert any('vllm==0.11.0' in c for c in commands)
    assert all('snapshot_download' not in str(c) for c in commands)


def test_download_only_selected_pinned_assets(tmp_path, monkeypatch):
    calls = []
    def fetch(model, **kwargs):
        calls.append((model, kwargs))
        return str(tmp_path / model.replace('/', '--'))
    monkeypatch.setitem(sys.modules, 'huggingface_hub', SimpleNamespace(snapshot_download=fetch))
    setup.main(['download', '--cache-dir', str(tmp_path), '--profile', SECOND, '--laya'])
    assert [c[0] for c in calls] == ['Qwen/Qwen3.5-9B', 'convaiinnovations/laya']
    assert all(len(c[1]['revision']) == 40 for c in calls)
    assert all(c[1]['cache_dir'] == str(tmp_path / 'hub') for c in calls)


def test_download_requires_selection():
    with pytest.raises(SystemExit):
        setup.main(['download', '--cache-dir', 'tmp/hf'])


def test_qwen35_uses_separate_compatible_environment(tmp_path):
    commands = setup.install_commands(tmp_path, 'actor', 'configs/models/qwen35-9b-a100.json')
    assert commands[0][-1] == str(tmp_path / 'actor-qwen35')
    assert 'vllm==0.19.1' in commands[1]
    assert 'transformers==5.6.2' in commands[1]
    assert not any('bitsandbytes' in part for command in commands for part in command)
