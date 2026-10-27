"""Reuse the existing Gatekeeper/Laya lifecycle and decision policy unchanged."""
import json
import os
from pathlib import Path
from blackbox.actions import canonical
from blackbox.contracts import GateDecision


COLLECTION_READS = {
    'search_calendar_events': 'calendar', 'get_day_calendar_events': 'calendar',
    'get_unread_emails': 'email', 'get_sent_emails': 'email',
    'get_received_emails': 'email', 'get_draft_emails': 'email', 'search_emails': 'email',
    'search_files_by_filename': 'drive', 'list_files': 'drive', 'search_files': 'drive',
}


def semantic_facts(tool, facts):
    """Collection reads need scope, not every resource's freshness hash.

    The wall and executor still consume the original frozen facts. This summary
    describes the collection being searched, never claims which events match,
    and preserves missing evidence and recipient information.
    """
    if tool not in COLLECTION_READS:
        return facts
    return {'collection': COLLECTION_READS[tool], 'scope': 'full_collection_not_search_results',
            'resource_count': len(facts.get('resources', [])),
            'missing': facts.get('missing', []), 'recipients': facts.get('recipients', [])}


def usage_diagnostics(raw):
    """Only numeric/bool diagnostics; never copy model input or free text."""
    usage = raw.get('usage', {}) if isinstance(raw, dict) else {}
    if not isinstance(usage, dict):
        return {}
    result = {key: usage[key] for key in ('state_tokens', 'state_tokens_used',
              'state_tokens_dropped', 'truncated') if type(usage.get(key)) in (int, bool)}
    if isinstance(usage.get('truncated_questions'), list):
        result['truncated_question_count'] = len(usage['truncated_questions'])
    result['option_collapse'] = bool(usage.get('options'))
    return result


class ExistingLayaGate:
    def __init__(self, config, max_chars):
        self.config = config
        self.max_chars = max_chars
        self.gate = None
        self.closed = False
        self.recorder = None
        self.backend_override = None

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

        self.gate = Gatekeeper(self.backend_override or LayaBackend(checkpoint=checkpoint, revision=revision,
            cache_dir=str(cache), timeout=self.config.timeout_seconds,
            load_timeout=self.config.load_timeout_seconds, question_mode='single',
            max_input_tokens=self.config.max_input_tokens, context_profile=self.config.input_profile,
            max_context_chars=self.max_chars),
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
                         'facts': {'metadata': (facts if self.config and self.config.input_profile in ('full_evidence', 'evidence_v2')
                                               else semantic_facts(action.tool, facts)), 'effects': list(action.effects),
                                   'provenance': 'native_schema_and_declared_metadata'}}}
            if self.config and self.config.input_profile == 'full_evidence':
                state['verified_context']['facts']['omitted_evidence'] = []
            if len(canonical(state)) > self.max_chars and not (self.config and self.config.input_profile == 'evidence_v2'):
                if self.recorder:
                    self.recorder('gate_input', {'action_id': action.action_id, 'input': state,
                                  'raw_output': None, 'error_kind': 'application_character_budget'})
                return GateDecision('ASK', 'APPLICATION_CHARACTER_BUDGET', backend='existing_laya',
                                    error_kind='application_character_budget')
            result = self.gate.evaluate(state)
            if self.recorder:
                self.recorder('gate_backend', {
                    'action_id': action.action_id,
                    'metadata': getattr(self.gate.backend, 'metadata', {}),
                })
                self.recorder('gate_input', {'action_id': action.action_id, 'input': state,
                    'raw_output': result.raw_model_output, 'error_kind': result.error_kind,
                    'error': result.error, 'model_called': result.model_called,
                    'context_diagnostics': result.context_diagnostics,
                    'final_decision': result.decision, 'reason': result.reason_code})
            return GateDecision(result.decision, result.reason_code, result.raw_model_decision,
                result.class_probabilities, 'existing_laya', 'single-v1',
                self.gate.backend.checkpoint, self.gate.backend.revision, result.error_kind,
                diagnostics={**usage_diagnostics(result.raw_model_output),
                             'context': result.context_diagnostics},
                initialization_error=getattr(self.gate.backend, 'metadata', {}).get('initialization_error'))
        except Exception as exc:
            initialization_error = f'{type(exc).__name__}: {exc}' if self.gate is None else None
            return GateDecision('ASK', 'MODEL_UNAVAILABLE', backend='existing_laya',
                                error_kind=type(exc).__name__, initialization_error=initialization_error)

    def close(self):
        self.closed = True
        if self.gate is not None:
            self.gate.close()
