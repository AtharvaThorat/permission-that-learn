"""Enforcement is independent of the semantic backend; nothing executes here."""
from dataclasses import dataclass
from time import perf_counter
from .schemas import Output, Request
from .validation import validate, exact_time_conflict
from .laya_adapter import Prediction

REASONS = {
    'INVALID_ACTION': 'The proposed action or its wall binding is invalid.',
    'INVALID_REQUEST': 'The request does not satisfy the input contract.',
    'WALL_DENIED': 'The wall denied this action.',
    'WALL_UNVERIFIED': 'No verified wall pass is available.',
    'TASK_MISMATCH': 'The proposed action is classified as contradicting the authentic task.',
    'CONFIRMATION_REQUIRED': 'A separate confirmation requirement applies.',
    'INSUFFICIENT_EVIDENCE': 'Decision evidence is explicitly incomplete.',
    'NEEDS_CLARIFICATION': 'The semantic classifier identified unresolved action details.',
    'TASK_AUTHORIZED': 'The semantic classifier supports this complete wall-approved action.',
    'UNCERTAIN': 'Authorization is uncertain.',
    'MODEL_UNAVAILABLE': 'No usable semantic decision is available.',
}

@dataclass
class GateDecision:
    output: Output
    model_called: bool = False
    raw_model_output: dict | None = None
    raw_model_decision: str | None = None
    class_probabilities: dict | None = None
    error: str | None = None
    error_kind: str | None = None
    path: str = 'deterministic_short_circuit'
    elapsed_seconds: float = 0
    model_elapsed_seconds: float | None = None
    raw_answers: dict | None = None
    probabilities_by_question: dict | None = None
    combined_semantic_decision: str | None = None
    truncated: bool | None = None
    model_call_count: int | None = 0
    model_call_submissions: int = 0
    context_diagnostics: dict | None = None

    @property
    def decision(self):
        return self.output.decision

    @property
    def reason_code(self):
        return self.output.reason_code


Evaluation = GateDecision  # Backward-compatible experiment record name.

class Gatekeeper:
    def __init__(self, backend=None, *, request_validator=None):
        from .laya_adapter import LayaBackend
        self.backend = backend if backend is not None else LayaBackend()
        # Trusted integration seam. Default prototype schemas/semantics stay intact.
        # An adapter may validate native tool schemas without renaming/lossy mapping.
        self.request_validator = request_validator or validate

    def initialize(self):
        self.backend.initialize()

    def close(self):
        self.backend.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def evaluate(self, raw) -> GateDecision:
        started = perf_counter()
        if isinstance(raw, Request):
            raw = raw.model_dump()
        req, invalid = self.request_validator(raw)
        raw_dict = raw if isinstance(raw, dict) else {}
        action = raw_dict.get('action', {})
        action = action if isinstance(action, dict) else {}
        record = Evaluation(Output(request_id=str(raw_dict.get('request_id', '')),
                                   action_id=str(action.get('action_id', '')),
                                   decision='BLOCK', reason_code='INVALID_REQUEST'))

        def finish(decision, reason):
            record.output = Output(request_id=record.output.request_id, action_id=record.output.action_id,
                                   decision=decision, reason_code=reason)
            record.elapsed_seconds = perf_counter() - started
            return record

        if invalid:
            return finish('BLOCK', invalid)
        if req.wall is None or req.wall.verdict in (None, 'UNKNOWN'):
            return finish('BLOCK', 'WALL_UNVERIFIED')
        if req.wall.verdict == 'DENY':
            return finish('BLOCK', 'WALL_DENIED')
        if exact_time_conflict(req):
            return finish('BLOCK', 'TASK_MISMATCH')

        # Query semantics before confirmation/evidence: a known contradiction wins.
        try:
            prediction = self.backend.predict(req)
            if not isinstance(prediction, Prediction):
                raise ValueError('Backend returned no typed prediction')
        except Exception as exc:
            prediction = Prediction(called=True, error=f'{type(exc).__name__}: {exc}',
                                    error_kind='inference_failure',
                                    model_call_count=None, model_call_submissions=1)
        record.model_called = prediction.called
        record.raw_model_output = prediction.raw
        record.raw_model_decision = prediction.raw_decision
        record.class_probabilities = prediction.probabilities
        record.error = prediction.error
        record.error_kind = prediction.error_kind
        record.model_elapsed_seconds = prediction.elapsed_seconds
        record.raw_answers = prediction.raw_answers
        record.probabilities_by_question = prediction.probabilities_by_question
        record.combined_semantic_decision = prediction.decision
        record.truncated = prediction.truncated
        record.model_call_count = prediction.model_call_count
        record.model_call_submissions = prediction.model_call_submissions
        record.context_diagnostics = prediction.context_diagnostics
        record.path = 'model_evaluated' if prediction.called else 'model_unavailable'
        if prediction.decision == 'BLOCK':
            return finish('BLOCK', 'TASK_MISMATCH')
        if req.verified_context.confirmation_required:
            return finish('ASK', 'CONFIRMATION_REQUIRED')
        if not req.verified_context.evidence_complete:
            return finish('ASK', 'INSUFFICIENT_EVIDENCE')
        if prediction.error or prediction.decision is None:
            return finish('ASK', 'MODEL_UNAVAILABLE')
        if prediction.decision == 'ALLOW':
            return finish('ALLOW', 'TASK_AUTHORIZED')
        if prediction.decision == 'ASK':
            return finish('ASK', prediction.ask_reason_code or 'NEEDS_CLARIFICATION')
        return finish('ASK', 'UNCERTAIN')
