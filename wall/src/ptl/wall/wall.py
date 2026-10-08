"""The Wall: turn a raw tool call into an Action and check it against the frozen policy."""

from __future__ import annotations

from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict

from .context import WallContext
from .inventory import ToolInventory
from .models import Action, TargetClass, Verdict
from .policy import WallPolicy, normalize_share_permission


class UnknownToolError(KeyError):
    """Raised when a tool is not in the inventory. The Wall treats this as a block."""


class WallResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    tool: str
    action: Action | None
    verdict: Verdict
    policy_fingerprint: str


class Wall:
    """Deterministic gate. Same tool call + same policy + same context = same verdict, always."""

    def __init__(self, policy: WallPolicy, context: WallContext, inventory: ToolInventory | None = None):
        self._policy = policy
        self._context = context
        self._inventory = inventory or ToolInventory.workspace()
        self._fingerprint = policy.fingerprint()

    @property
    def policy(self) -> WallPolicy:
        return self._policy

    @property
    def context(self) -> WallContext:
        return self._context

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    def to_action(self, tool: str, args: Mapping[str, Any]) -> Action:
        spec = self._inventory.get(tool)
        if spec is None:
            raise UnknownToolError(tool)

        addresses: list[str] = []
        targets: list[TargetClass] = []
        for arg in spec.target_args:
            value = args.get(arg)
            if value is None:
                continue
            items = value if isinstance(value, (list, tuple)) else [value]
            for item in items:
                addresses.append(str(item))
                targets.append(self._context.classify(item))

        has_attachments = bool(args.get(spec.attachment_arg)) if spec.attachment_arg else False
        permission = (
            normalize_share_permission(args.get(spec.permission_arg)) if spec.permission_arg else None
        )
        return Action(
            tool=tool,
            capability=spec.capability,
            targets=tuple(targets),
            target_addresses=tuple(addresses),
            has_attachments=has_attachments,
            share_permission=permission,
        )

    def evaluate(self, tool: str, args: Mapping[str, Any] | None = None) -> WallResult:
        args = args or {}
        try:
            action = self.to_action(tool, args)
        except UnknownToolError:
            verdict = Verdict(allowed=False, reasons=(f"unknown tool '{tool}' is not in the inventory",))
            return WallResult(tool=tool, action=None, verdict=verdict, policy_fingerprint=self._fingerprint)
        return WallResult(
            tool=tool,
            action=action,
            verdict=self._policy.check(action),
            policy_fingerprint=self._fingerprint,
        )
