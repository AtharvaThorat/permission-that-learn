"""Grant-backed answers to optional judgment asks through the existing controller."""
import json
from .approvals import ApprovalEvent
from .memory import ELIGIBLE_REASONS
from .store import scope_for
from grids.core.contracts import Outcome


class ScopedApprovalProvider:
    def __init__(self, inner, store, user, mode='shadow', frozen=False, record=None):
        self.inner, self.store, self.user = inner, store, store.user(user)
        self.mode, self.frozen, self.record = mode, frozen, record
        self.decision_id = None

    def request(self, pending):
        self.decision_id = None
        metadata = json.loads(pending.decision_metadata)
        if (pending.reason not in ELIGIBLE_REASONS or metadata.get('error_kind')
                or not pending.action.evidence_complete):
            return self.inner.request(pending)
        scope = scope_for(pending.request, pending.action)
        try:
            decision_id, permit, record = self.store.decide(self.user, scope, pending.binding,
                metadata.get('probabilities'), pending.action.effects, self.mode, self.frozen, metadata)
        except ValueError as exc:
            if str(exc) != 'INVALID_PROBABILITIES':
                raise
            return self.inner.request(pending)
        self.decision_id = decision_id
        if self.record:
            self.record({'decision_id': decision_id, 'user': self.user, **record})
        if permit:
            return ApprovalEvent(pending.pending_id, pending.binding, True, permit)
        feedback = self.inner.request(pending)
        if (isinstance(feedback, ApprovalEvent) and type(feedback.approved) is bool
                and feedback.pending_id == pending.pending_id and feedback.binding == pending.binding):
            self.store.operational(self.user, decision_id, feedback.approved)
        if feedback is None:
            self.observe(Outcome(False, pending.reason, 'ASK', terminal='pending_approval'))
        return feedback

    def observe(self, outcome):
        if self.decision_id:
            self.store.outcome(self.user, self.decision_id, outcome)
