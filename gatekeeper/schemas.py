"""Strict contract types; fixture metadata is deliberately not accepted."""
from typing import Any, Literal, Annotated
from pydantic import BaseModel, ConfigDict, Field

Decision = Literal['ALLOW', 'ASK', 'BLOCK']
Reason = Literal['INVALID_ACTION', 'INVALID_REQUEST', 'WALL_DENIED', 'WALL_UNVERIFIED',
                 'TASK_MISMATCH', 'CONFIRMATION_REQUIRED', 'INSUFFICIENT_EVIDENCE',
                 'NEEDS_CLARIFICATION', 'TASK_AUTHORIZED', 'UNCERTAIN', 'MODEL_UNAVAILABLE']
Nonempty = Annotated[str, Field(min_length=1)]

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

class Action(StrictModel):
    action_id: Nonempty
    tool: Nonempty
    arguments: dict[str, Any]

class Wall(StrictModel):
    verdict: Literal['PASS', 'DENY', 'UNKNOWN'] | None = None
    policy_version: Nonempty
    evaluated_action_id: Nonempty
    reason_codes: list[str]

class Context(StrictModel):
    confirmation_required: bool
    evidence_complete: bool
    facts: dict[str, Any]

class Request(StrictModel):
    schema_version: Literal['0.1']
    request_id: Nonempty
    task_id: Nonempty
    user_request: Nonempty
    action: Action
    wall: Wall | None = None
    verified_context: Context

class Output(StrictModel):
    request_id: str
    action_id: str
    decision: Decision
    reason_code: Reason
