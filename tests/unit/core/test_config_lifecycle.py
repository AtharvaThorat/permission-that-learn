"""No model downloads/initialization at collection time. NOT RUN."""
import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from grids.core.actions import canonical, parse_json
from grids.core.config import Config, load_config
from grids.core.contracts import Dependencies, GateDecision
from grids.core.factory import build_agentdojo_pipeline
from grids.core.permissions.gatekeeper_adapter import ExistingLayaGate
from .helpers import call, fixture, reply, run

@pytest.mark.parametrize('raw', [{'typo': 1}, {'learning_enabled': True}, {'simulation_only': False},
    {'mode': 'learned'}, {'actor': {'backend': 'paid_fallback'}},
    {'gatekeeper': {'allow_downloads': True}}, {'runtime': {'max_actor_turns': 0}},
    {'agentdojo': {'attack_name': 'fixed_file'}}, {'actor': {'base_url': 'https://key:secret@example.com/v1'}}])
def test_invalid_configuration_rejected(raw):
    with pytest.raises(ValidationError):
        Config.model_validate(raw)

def test_empty_selection_never_runs_all_tasks():
    with pytest.raises(ValueError, match='No user tasks'):
        Config().require_selection()

def test_factory_is_lazy(monkeypatch, tmp_path):
    import httpx
    from grids.gatekeeper.laya_adapter import LayaBackend
    def forbidden(*args, **kwargs):
        raise AssertionError('Unexpected model/network initialization')
    monkeypatch.setattr(httpx.Client, '__init__', forbidden)
    monkeypatch.setattr(LayaBackend, 'initialize', forbidden)
    config = load_config('tests/fixtures/runtime/wall_gatekeeper.json')
    config.audit.output_directory = str(tmp_path)
    pipeline = build_agentdojo_pipeline(config)
    assert pipeline.actor.client is None and pipeline.gate.gate is None
    assert not list(tmp_path.iterdir())
    pipeline.close()

def test_missing_local_assets_fails_without_backend(monkeypatch, tmp_path):
    from grids.gatekeeper.laya_adapter import LayaBackend
    monkeypatch.setenv('HF_HUB_OFFLINE', '1')
    monkeypatch.setenv('TRANSFORMERS_OFFLINE', '1')
    def forbidden(*args, **kwargs):
        raise AssertionError('Must fail before backend construction')
    monkeypatch.setattr(LayaBackend, '__init__', forbidden)
    config = Config()
    config.gatekeeper.cache_dir = str(tmp_path)
    gate = ExistingLayaGate(config.gatekeeper, 24000)
    with pytest.raises(FileNotFoundError, match='LOCAL_LAYA_SNAPSHOT_MISSING'):
        gate.initialize()

LAYA_REVISION = '7b928d828b7b0e022f929d9bd2e44165aa270148'


def _snapshot(tmp_path, *, encoder=True, nested=True):
    # File layout verified against the pinned Hugging Face tree:
    # https://huggingface.co/convaiinnovations/laya/tree/7b928d828b7b0e022f929d9bd2e44165aa270148
    snapshot = tmp_path / 'hub' / 'models--convaiinnovations--laya' / 'snapshots' / LAYA_REVISION
    snapshot.mkdir(parents=True)
    for name in ('config.json', 'model.safetensors'):
        (snapshot / name).write_text('{}')
    tokenizer = snapshot / 'tokenizer' if nested else snapshot
    tokenizer.mkdir(exist_ok=True)
    for name in ('tokenizer_config.json', 'tokenizer.json'):
        (tokenizer / name).write_text('{}')
    if encoder:
        (snapshot / 'encoder').mkdir()
        (snapshot / 'encoder' / 'config.json').write_text('{}')
    return tmp_path, snapshot

@pytest.mark.parametrize('nested', [True, False])
def test_local_laya_snapshot_resolves_pinned_assets(tmp_path, nested):
    from grids.gatekeeper.laya_adapter import resolve_local_snapshot
    cache, snapshot = _snapshot(tmp_path, nested=nested)
    assert resolve_local_snapshot('convaiinnovations/laya', LAYA_REVISION, cache) == snapshot

def test_local_laya_snapshot_rejects_missing_assets(tmp_path):
    from grids.gatekeeper.laya_adapter import resolve_local_snapshot
    cache, snapshot = _snapshot(tmp_path, encoder=False)
    with pytest.raises(FileNotFoundError, match='LOCAL_LAYA_SNAPSHOT_INVALID'):
        resolve_local_snapshot('convaiinnovations/laya', LAYA_REVISION, cache)


@pytest.mark.parametrize('missing', ['config.json', 'model.safetensors',
                                   'tokenizer/tokenizer_config.json', 'tokenizer/tokenizer.json'])
def test_local_laya_snapshot_rejects_incomplete_real_layout(tmp_path, missing):
    from grids.gatekeeper.laya_adapter import resolve_local_snapshot
    cache, snapshot = _snapshot(tmp_path)
    (snapshot / missing).unlink()
    with pytest.raises(FileNotFoundError, match='LOCAL_LAYA_SNAPSHOT_INVALID'):
        resolve_local_snapshot('convaiinnovations/laya', LAYA_REVISION, cache)


def test_gate_initialization_error_persisted_in_decision_event(tmp_path):
    from grids.core.audit import JsonlAudit
    from grids.gatekeeper.policy import Gatekeeper
    from grids.gatekeeper.schemas import Request
    from grids.gatekeeper.laya_adapter import Prediction

    error = 'RuntimeError: LOCAL_LAYA_SNAPSHOT_INVALID: missing tokenizer_config.json'

    class Backend:
        checkpoint, revision = 'convaiinnovations/laya', LAYA_REVISION
        def __init__(self):
            self.metadata = {}

        def predict(self, request):
            self.metadata['initialization_error'] = error
            return Prediction(error=error, error_kind='download_or_load_failure')

        def close(self):
            pass

    path = tmp_path / 'events.jsonl'
    f = fixture(audit=JsonlAudit(path))
    adapter = ExistingLayaGate(f.pipeline.config.gatekeeper, 24000)
    adapter.gate = Gatekeeper(Backend(), request_validator=lambda raw: (Request.model_validate(raw), None))
    f.pipeline.gate = adapter
    with f.pipeline:
        run(f)
    events = [json.loads(line) for line in path.read_text().splitlines()]
    decision = next(event for event in events if event['event'] == 'gate_decision')
    assert decision['initialization_error'] == error
    assert decision['error_kind'] == 'download_or_load_failure'
    assert decision['decision'] == 'ASK' and decision['reason_code'] == 'MODEL_UNAVAILABLE'
    assert not f.runtime.calls

def test_local_laya_snapshot_rejects_unknown_revision(tmp_path):
    from grids.gatekeeper.laya_adapter import resolve_local_snapshot
    _snapshot(tmp_path)
    with pytest.raises(FileNotFoundError, match='LOCAL_LAYA_SNAPSHOT_MISSING'):
        resolve_local_snapshot('convaiinnovations/laya', '8b' * 20, tmp_path)


@pytest.mark.parametrize('limit', [None, 8192])
def test_worker_accepts_pinned_local_snapshot_when_laya_revision_is_none(tmp_path, monkeypatch, limit):
    import sys
    from types import SimpleNamespace
    from grids.gatekeeper.laya_adapter import _worker
    cache, snapshot = _snapshot(tmp_path)
    class Agent:
        revision, device, cfg, dtype = None, 'cpu', {'max_len': 512}, 'float32'
        def __init__(self, **kwargs):
            assert kwargs['model_id_or_path'] == str(snapshot)
            assert kwargs['revision'] == LAYA_REVISION
        def system_one(self, state, questions, **kwargs):
            assert state == 'complete evidence'
            assert kwargs == ({} if limit is None else {'max_len': limit})
            return {'forward_pass': True}
    class Pipe:
        def __init__(self):
            self.sent = []
            self.requests = iter(['complete evidence', None])
        def send(self, value):
            self.sent.append(value)
        def recv(self):
            return next(self.requests)
        def close(self):
            pass
    monkeypatch.setitem(sys.modules, 'laya', SimpleNamespace(Agent=Agent))
    monkeypatch.setattr('grids.gatekeeper.laya_adapter.importlib.metadata.version', lambda name: 'test')
    monkeypatch.setattr('grids.gatekeeper.laya_adapter.preflight', lambda agent, state, *args, **kwargs: (state, {}))
    pipe = Pipe()
    _worker(pipe, 'convaiinnovations/laya', LAYA_REVISION, str(snapshot), str(cache), 'single', limit)
    assert pipe.sent[0]['ready'] is True
    assert pipe.sent[0]['revision'] == LAYA_REVISION
    assert pipe.sent[0]['agent_reported_revision'] is None
    assert pipe.sent[1] == {'raw': {'forward_pass': True}, 'api_calls': 1, 'context_diagnostics': {}}
    wrong = Pipe()
    _worker(wrong, 'convaiinnovations/laya', LAYA_REVISION, str(snapshot.parent), str(cache), 'single')
    assert 'Worker snapshot does not match' in wrong.sent[0]['error']

def test_cleanup_on_error_and_close_idempotent():
    f = fixture([{'role': 'invalid'}])
    with f.pipeline:
        run(f)
    f.pipeline.close()
    assert f.actor.closed and f.gate.closed

def test_reference_wall_and_raw_redaction():
    f = fixture([reply(call('send_email', {'recipients': ['known@example.com'],
        'subject': 'PRIVATE_SUBJECT', 'body': 'PRIVATE_BODY'})), reply(content='Done.')])
    run(f)
    audit = json.dumps(f.audit.events)
    assert f.wall.implementation == 'reference'
    assert 'PRIVATE_BODY' not in audit and 'PRIVATE_SUBJECT' not in audit
    assert 'SCRIPTED_TEST' in audit

def test_json_preserves_case_order_and_rejects_ambiguous_values():
    assert canonical({'body': 'Keep CASE', 'to': ['b', 'a']}) == '{"body":"Keep CASE","to":["b","a"]}'
    assert canonical({'x': None}) != canonical({})
    for value in (float('nan'), float('inf'), object()):
        with pytest.raises(ValueError):
            canonical(value)
    with pytest.raises(ValueError, match='DUPLICATE_JSON_KEY'):
        parse_json('{"a": 1, "a": 2}')

def test_unprotected_explicit_mode_bypasses_wall_only_in_simulation():
    f = fixture([reply(call('delete_file')), reply(content='Done.')], mode='unprotected')
    run(f)
    assert len(f.runtime.calls) == 1 and not f.gate.calls

def test_existing_gate_semantics_reused_for_native_tool():
    from grids.gatekeeper.policy import Gatekeeper
    from grids.gatekeeper.schemas import Request
    from grids.gatekeeper.laya_adapter import Prediction
    class Backend:
        checkpoint, revision = 'test', '0' * 40
        def predict(self, request):
            assert request.action.tool == 'get_file_by_id'
            return Prediction(decision='ALLOW', raw_decision='ALLOW', called=True)
        def close(self):
            pass
    # The integration validator is independently tested via a real adapter request.
    f = fixture()
    adapter = ExistingLayaGate(f.pipeline.config.gatekeeper, 24000)
    adapter.gate = Gatekeeper(Backend(), request_validator=lambda raw: (Request.model_validate(raw), None))
    f.pipeline.gate = adapter
    run(f)
    assert len(f.runtime.calls) == 1

def test_no_implicit_provider_fallback(monkeypatch):
    from grids.actors.client.openai_compatible import OpenAICompatibleActor
    monkeypatch.delenv('GRIDS_ACTOR_API_KEY', raising=False)
    actor = OpenAICompatibleActor(Config().actor)
    try:
        with pytest.raises(RuntimeError, match='CREDENTIAL_ENV_MISSING'):
            actor.respond([], [], 1)
    finally:
        actor.close()
