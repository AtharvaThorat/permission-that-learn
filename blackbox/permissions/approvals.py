from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4
from .bindings import Binding

@dataclass(frozen=True)
class PendingApproval:
    pending_id: str
    binding: Binding
    action: object  # Immutable BoundAction contains the exact argument snapshot.
    reason: str

@dataclass(frozen=True)
class ApprovalEvent:
    pending_id: str
    binding: Binding
    approved: bool

class ApprovalProvider(Protocol):
    def request(self, pending: PendingApproval) -> ApprovalEvent | None: ...

class PendingApprovalProvider:
    def request(self, pending):
        return None

class ScriptedApprovalProvider:
    """Trusted test feedback only; events must match an exact pending binding."""
    def __init__(self, events):
        self.events = iter(events)

    def request(self, pending):
        event = next(self.events, None)
        # Callables let deterministic tests construct an event using its fresh ID.
        return event(pending) if callable(event) else event

def pending_record(episode, action, reason, expires):
    return PendingApproval(uuid4().hex, Binding.create(episode, action, expires), action, reason)
