"""Dependency-light contracts; arguments are frozen as canonical JSON strings."""
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

DecisionLabel = Literal['ALLOW', 'ASK', 'BLOCK']

@dataclass(frozen=True)
class Proposal:
    call_id: str
    tool: str
    arguments: dict
    original_call_id: str | None = None

@dataclass(frozen=True)
class BoundAction:
    action_id: str
    call_id: str
    tool: str
    original_json: str
    arguments_json: str
    digest: str
    effects: tuple[str, ...]
    facts_json: str
    state_version: str
    policy_version: str
    evidence_complete: bool
    schema_digest: str

@dataclass(frozen=True)
class WallVerdict:
    verdict: Literal['PASS', 'DENY', 'UNRESOLVED']
    reason: str
    policy_version: str
    digest: str
    state_version: str
    confirmation_required: bool = False
    missing: tuple[str, ...] = ()

@dataclass(frozen=True)
class GateDecision:
    decision: DecisionLabel
    reason: str
    raw_recommendation: str | None = None
    probabilities: dict | None = None
    backend: str = 'none'
    prompt_version: str | None = None
    checkpoint: str | None = None
    revision: str | None = None
    error_kind: str | None = None
    calibration: str = 'unknown'
    diagnostics: dict | None = None

@dataclass(frozen=True)
class Outcome:
    executed: bool
    reason: str
    decision: str
    result: Any = None
    error: str | None = None
    terminal: str | None = None
    state_version: str | None = None

class Actor(Protocol):
    def respond(self, messages: list[dict], tools: list[dict], timeout: float) -> dict: ...
    def close(self) -> None: ...

class Gate(Protocol):
    def evaluate(self, episode, action: BoundAction, wall: WallVerdict) -> GateDecision: ...
    def close(self) -> None: ...

class AuditSink(Protocol):
    def emit(self, event: dict) -> None: ...

@dataclass
class Dependencies:
    actor: Any = None
    wall: Any = None
    gatekeeper: Any = None
    clock: Any = None
    approvals: Any = None
    facts: Any = None
    executor: Any = None
    audit: Any = None
    run_id: str | None = None
    metadata: dict = field(default_factory=dict)
