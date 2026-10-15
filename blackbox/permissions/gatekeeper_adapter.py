"""Reuse the existing Gatekeeper/Laya lifecycle and decision policy unchanged."""
import json
import os
from pathlib import Path
from blackbox.actions import canonical
from blackbox.contracts import GateDecision

class ExistingLayaGate:
    def __init__(self, config, max_chars):
        self.config = config
        self.max_chars = max_chars
        self.gate = None
        self.closed = False

    def initialize(self):
        if self.closed:
            raise RuntimeError('GATE_CLOSED')
        if self.gate is not None:
            return
        # Fail before constructing the backend unless the user explicitly opted
        # into offline local cache use. The worker inherits these settings.
        if os.environ.get('HF_HUB_OFFLINE') != '1' or os.environ.get('TRANSFORMERS_OFFLINE') != '1':
            raise RuntimeError('OFFLINE_ENV_REQUIRED')
        cache = Path(self.config.cache_dir or '')
        from gatekeeper.config import resolve_checkpoint
        checkpoint, revision = resolve_checkpoint(profile='baseline')
        snapshot = cache / 'hub' / ('models--' + checkpoint.replace('/', '--')) / 'snapshots' / revision
        if not self.config.cache_dir or not snapshot.is_dir():
            raise FileNotFoundError('LOCAL_LAYA_SNAPSHOT_MISSING')
        from gatekeeper.policy import Gatekeeper
        from gatekeeper.laya_adapter import LayaBackend
        from gatekeeper.schemas import Request

        def native_request(raw):
            try:
                req = Request.model_validate(raw)
                if req.wall is None or req.wall.evaluated_action_id != req.action.action_id:
                    return None, 'INVALID_ACTION'
                # Arguments already validated and frozen against the supplied native
                # runtime by the controller, then privately constructed below.
                canonical(req.action.arguments)
                if req.action.tool not in self._native_schemas:
                    return None, 'INVALID_ACTION'
                schema = self._native_schemas[req.action.tool]
                normalized = schema.model_validate(req.action.arguments).model_dump(mode='json')
                if canonical(normalized) != canonical(req.action.arguments):
                    return None, 'INVALID_ACTION'
                return req, None
            except ValueError:
                return None, 'INVALID_REQUEST'

        self.gate = Gatekeeper(LayaBackend(checkpoint=checkpoint, revision=revision,
            cache_dir=str(cache), timeout=self.config.timeout_seconds,
            load_timeout=self.config.load_timeout_seconds, question_mode='single'),
            request_validator=native_request)
        # Existing evaluate() lazily initializes and reuses its persistent worker.

    def set_native_schemas(self, runtime):
        # Private trusted registry for this sequential episode. Models cannot set it.
        self._native_schemas = {name: tool.parameters for name, tool in runtime.functions.items()}

    def evaluate(self, episode, action, wall):
        try:
            self.initialize()
            facts = json.loads(action.facts_json)
            state = {'schema_version': '0.1', 'request_id': action.action_id,
                     'task_id': episode.episode_id, 'user_request': episode.task,
                     'action': {'action_id': action.action_id, 'tool': action.tool,
                                'arguments': json.loads(action.arguments_json)},
                     'wall': {'verdict': 'PASS', 'policy_version': wall.policy_version,
                              'evaluated_action_id': action.action_id, 'reason_codes': [wall.reason]},
                     'verified_context': {'confirmation_required': wall.confirmation_required,
                         'evidence_complete': action.evidence_complete,
                         'facts': {'metadata': facts, 'effects': list(action.effects),
                                   'provenance': 'native_schema_and_declared_metadata'}}}
            if len(canonical(state)) > self.max_chars:
                return GateDecision('ASK', 'INCOMPLETE_EVIDENCE', backend='existing_laya')
            result = self.gate.evaluate(state)
            return GateDecision(result.decision, result.reason_code, result.raw_model_decision,
                result.class_probabilities, 'existing_laya', 'single-v1',
                self.gate.backend.checkpoint, self.gate.backend.revision, result.error_kind)
        except Exception as exc:
            return GateDecision('ASK', 'MODEL_UNAVAILABLE', backend='existing_laya', error_kind=type(exc).__name__)

    def close(self):
        self.closed = True
        if self.gate is not None:
            self.gate.close()
