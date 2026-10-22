"""No model downloads/initialization at collection time. NOT RUN."""
import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from blackbox.actions import canonical, parse_json
from blackbox.config import Config, load_config
from blackbox.contracts import Dependencies, GateDecision
from blackbox.factory import build_agentdojo_pipeline
from blackbox.permissions.gatekeeper_adapter import ExistingLayaGate
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
    from gatekeeper.laya_adapter import LayaBackend
    def forbidden(*args, **kwargs):
        raise AssertionError('Unexpected model/network initialization')
    monkeypatch.setattr(httpx, 'Client', forbidden)
    monkeypatch.setattr(LayaBackend, 'initialize', forbidden)
    config = load_config('configs/blackbox/wall_gatekeeper.json')
    config.audit.output_directory = str(tmp_path)
    pipeline = build_agentdojo_pipeline(config)
    assert pipeline.actor.client is None and pipeline.gate.gate is None
    assert not list(tmp_path.iterdir())
    pipeline.close()

def test_missing_local_assets_fails_without_backend(monkeypatch, tmp_path):
    from gatekeeper.laya_adapter import LayaBackend
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

def _snapshot(tmp_path, *, encoder=True):
    snapshot = tmp_path / 'hub' / 'models--convaiinnovations--laya' / 'snapshots' / ('7b' * 20)
    snapshot.mkdir(parents=True)
    for name in ('config.json', 'tokenizer_config.json', 'tokenizer.json', 'model.safetensors'):
        (snapshot / name).write_text('{}')
    if encoder:
        (snapshot / 'encoder_config.json').write_text('{}')
    return tmp_path, snapshot

def test_local_laya_snapshot_resolves_pinned_assets(tmp_path):
    from gatekeeper.laya_adapter import resolve_local_snapshot
    cache, snapshot = _snapshot(tmp_path)
    assert resolve_local_snapshot('convaiinnovations/laya', '7b' * 20, cache) == snapshot

def test_local_laya_snapshot_rejects_missing_assets(tmp_path):
    from gatekeeper.laya_adapter import resolve_local_snapshot
    cache, snapshot = _snapshot(tmp_path, encoder=False)
    with pytest.raises(FileNotFoundError, match='LOCAL_LAYA_SNAPSHOT_INVALID'):
        resolve_local_snapshot('convaiinnovations/laya', '7b' * 20, cache)

def test_local_laya_snapshot_rejects_unknown_revision(tmp_path):
    from gatekeeper.laya_adapter import resolve_local_snapshot
    _snapshot(tmp_path)
    with pytest.raises(FileNotFoundError, match='LOCAL_LAYA_SNAPSHOT_MISSING'):
        resolve_local_snapshot('convaiinnovations/laya', '8b' * 20, tmp_path)

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
    from gatekeeper.policy import Gatekeeper
    from gatekeeper.schemas import Request
    from gatekeeper.laya_adapter import Prediction
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
    from blackbox.actors.openai_compatible import OpenAICompatibleActor
    monkeypatch.delenv('BLACKBOX_ACTOR_API_KEY', raising=False)
    actor = OpenAICompatibleActor(Config().actor)
    try:
        with pytest.raises(RuntimeError, match='CREDENTIAL_ENV_MISSING'):
            actor.respond([], [], 1)
    finally:
        actor.close()
