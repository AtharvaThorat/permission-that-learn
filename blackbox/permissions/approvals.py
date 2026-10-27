from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import time
from typing import Protocol
from uuid import uuid4
from .bindings import Binding

@dataclass(frozen=True)
class PendingApproval:
    pending_id: str
    binding: Binding
    action: object  # Immutable BoundAction contains the exact argument snapshot.
    reason: str
    decision_metadata: str = '{}'
    created_at: str = ''
    expires_at: str = ''
    continuation: str = 'live_process_only'

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

def pending_record(episode, action, reason, expires, *, decision=None, remaining=None):
    now = datetime.now(timezone.utc)
    return PendingApproval(uuid4().hex, Binding.create(episode, action, expires), action, reason,
        json.dumps(decision or {}, sort_keys=True), now.isoformat(),
        (now + timedelta(seconds=max(0, remaining))).isoformat() if remaining is not None else '')


def exclusive_json(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())


class FileApprovalProvider:
    """Trusted operator channel; only the live episode can consume feedback."""
    def __init__(self, directory, wait_seconds=0, cancellation=None):
        if not 0 <= wait_seconds <= 3600:
            raise ValueError('Approval wait must be between 0 and 3600 seconds')
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.wait_seconds, self.cancellation = wait_seconds, cancellation
        self.consumed = set()

    def request(self, pending):
        if pending.pending_id in self.consumed:
            return None
        exclusive_json(self.directory / (pending.pending_id + '.json'), asdict(pending))
        deadline = min(pending.binding.expires, time.monotonic() + self.wait_seconds)
        response = self.directory / (pending.pending_id + '.response.json')
        while time.monotonic() < deadline:
            if self.cancellation and self.cancellation.is_set():
                return None
            if response.exists():
                value = json.loads(response.read_text(encoding='utf-8'))
                if set(value) != {'pending_id', 'binding', 'approved'} or type(value['approved']) is not bool:
                    raise ValueError('Invalid approval response')
                self.consumed.add(pending.pending_id)
                return ApprovalEvent(value['pending_id'], Binding(**value['binding']), value['approved'])
            time.sleep(min(0.1, max(0, deadline - time.monotonic())))
        return None


def respond(pending_path, approved):
    path = Path(pending_path)
    pending = json.loads(path.read_text(encoding='utf-8'))
    if not pending.get('expires_at') or datetime.now(timezone.utc) >= datetime.fromisoformat(pending['expires_at']):
        raise ValueError('Approval request expired; restarting an episode cannot continue this action')
    response = path.with_name(pending['pending_id'] + '.response.json')
    if path.name != pending['pending_id'] + '.json':
        raise ValueError('Pending filename/identity mismatch')
    exclusive_json(response, {'pending_id': pending['pending_id'], 'binding': pending['binding'], 'approved': approved})
    return str(response)
