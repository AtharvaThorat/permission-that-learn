import json
import pytest

from blackbox.permissions.approvals import FileApprovalProvider, respond
from experiment.artifacts import Writer
from tests.blackbox.helpers import fixture, run


class Environment(dict):
    def model_dump(self, **kwargs):
        return dict(self)


@pytest.mark.parametrize('approved', [True, False])
def test_operator_feedback_is_bound_and_pending_is_durable(tmp_path, monkeypatch, approved):
    inbox = tmp_path / 'operator'
    provider = FileApprovalProvider(inbox, wait_seconds=5)
    f = fixture(labels=('ASK',), approvals=provider)
    f.env = Environment(f.env)
    writer = Writer(tmp_path)
    f.pipeline.dependencies.trace = writer
    monkeypatch.setattr('blackbox.permissions.approvals.time.monotonic', f.clock.monotonic)
    def operator(_):
        path = next(inbox.glob('*.json'))
        pending = json.loads(path.read_text())
        durable = tmp_path / 'pending' / '1.json'
        assert json.loads(durable.read_text()) == pending
        assert not f.runtime.calls
        assert pending['binding']['attempt_id']
        assert pending['action']['arguments_json'] == '{"file_id":"notes-7"}'
        respond(path, approved)
        with pytest.raises(FileExistsError):
            respond(path, approved)
    monkeypatch.setattr('blackbox.permissions.approvals.time.sleep', operator)
    run(f)
    assert len(f.runtime.calls) == int(approved)
    pending = f.pipeline.last_episode.pending[0]
    assert provider.request(pending) is None
    writer.close()


def test_pending_write_failure_prevents_dispatch(tmp_path):
    f = fixture(labels=('ASK',))
    f.env = Environment(f.env)
    writer = Writer(tmp_path)
    (tmp_path / 'pending').write_text('not a directory')
    f.pipeline.dependencies.trace = writer
    run(f)
    assert not f.runtime.calls
    assert f.pipeline.last_episode.terminal == 'infrastructure_error'
    writer.close()


def test_unattended_pending_does_not_wait(tmp_path):
    provider = FileApprovalProvider(tmp_path / 'operator')
    f = fixture(labels=('ASK',), approvals=provider)
    run(f)
    assert not f.runtime.calls
    assert f.pipeline.last_episode.terminal == 'pending_approval'
    assert len(list((tmp_path / 'operator').glob('*.json'))) == 1
