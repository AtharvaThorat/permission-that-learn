import json
import pytest
from grids.actors import preflight
from grids.cli import setup

PROFILE = 'configs/models/qwen35-9b-a100.json'


def linux(monkeypatch, version='2.31'):
    monkeypatch.setattr(preflight.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(preflight.platform, 'machine', lambda: 'x86_64')
    monkeypatch.setattr(preflight.platform, 'libc_ver', lambda: ('glibc', version))
    monkeypatch.setattr(preflight.sys, 'version_info', (3, 12, 10))


def test_old_glibc_prevents_install(tmp_path, monkeypatch):
    linux(monkeypatch, '2.28')
    monkeypatch.setattr(setup.subprocess, 'run', lambda *a, **kw: pytest.fail('Started installation'))
    with pytest.raises(RuntimeError, match='ACTOR_GLIBC_UNSUPPORTED'):
        setup.main(['install', '--component', 'actor', '--profile', PROFILE, '--work-dir', str(tmp_path)])


def test_binary_resolution_failure_prevents_install(tmp_path, monkeypatch):
    linux(monkeypatch)
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        if '--dry-run' in command:
            raise setup.subprocess.CalledProcessError(1, command)
    monkeypatch.setattr(setup.subprocess, 'run', run)
    with pytest.raises(setup.subprocess.CalledProcessError):
        setup.main(['install', '--component', 'actor', '--profile', PROFILE, '--work-dir', str(tmp_path)])
    assert len(calls) == 2 and '--only-binary=:all:' in calls[-1]


def test_failed_preflight_records_host_and_refuses_overwrite(tmp_path, monkeypatch):
    linux(monkeypatch, '2.28')
    output = tmp_path / 'preflight.json'
    args = ['--profile', PROFILE, '--output', str(output)]
    assert preflight.main(args) == 1
    data = json.loads(output.read_text())
    assert data['libc_version'] == '2.28' and data['status'] == 'failed'
    assert 'ACTOR_GLIBC_UNSUPPORTED' in data['error']
    with pytest.raises(FileExistsError):
        preflight.main(args)


def test_wrong_package_rejected(monkeypatch):
    linux(monkeypatch)
    monkeypatch.setattr(preflight.importlib.metadata, 'version', lambda name: 'wrong')
    with pytest.raises(RuntimeError, match='PROFILE_PACKAGE_MISMATCH'):
        preflight.check_runtime(preflight.load_profile(PROFILE))
