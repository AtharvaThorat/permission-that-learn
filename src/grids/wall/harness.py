"""Bind deterministic Wall policies to GRIDS actions and verified state."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from typing import Any

from .context import WallContext
from .inventory import ToolInventory
from .models import Capability, WallDecision
from .policy import WallPolicy
from .wall import Wall

# The harness says UNRESOLVED where this package says UNKNOWN; same meaning.
_HARNESS_LABEL = {WallDecision.PASS: "PASS", WallDecision.DENY: "DENY", WallDecision.UNKNOWN: "UNRESOLVED"}
PASS_REASON = "WALL_PASS"


def _harness_verdict_class() -> Callable[..., Any]:
    from grids.core.contracts import WallVerdict  # imported lazily: only needed inside the harness

    return WallVerdict


class HarnessWall:
    """The Wall behind the harness's `Wall` protocol.

    `context` is the trust snapshot. AgentDojo starts every Workspace task from the same inbox,
    calendar and drive (injection tasks only change text), so one snapshot of the clean default
    environment is correct for every task; `for_agentdojo_workspace` builds it.

    `confirm_capabilities` marks PASS actions that still need the user's confirmation
    (`WallVerdict.confirmation_required`), which the harness turns into ASK. Empty by default:
    the Wall itself only decides PASS / DENY / UNRESOLVED.
    """

    implementation = "ptl"

    def __init__(
        self,
        policy: WallPolicy,
        context: WallContext,
        *,
        inventory: ToolInventory | None = None,
        confirm_capabilities: Iterable[Capability | str] = (),
        verdict_class: Callable[..., Any] | None = None,
    ):
        self._wall = Wall(policy, context, inventory)
        self._confirm = frozenset(Capability(c) for c in confirm_capabilities)
        self._verdict_class = verdict_class

    @classmethod
    def for_agentdojo_workspace(cls, policy: WallPolicy, *, suite_version: str = "v1.2.2",
                                extra_domains: Iterable[str] = (), **kwargs: Any) -> HarnessWall:
        """Snapshot AgentDojo's clean default Workspace environment once and wrap the policy."""
        from agentdojo.task_suite.load_suites import get_suite

        env = get_suite(suite_version, "workspace").load_and_inject_default_environment({})
        return cls(policy, WallContext.from_agentdojo_env(env, extra_domains), **kwargs)

    @property
    def wall(self) -> Wall:
        return self._wall

    @property
    def version(self) -> str:
        """Policy fingerprint + trust-snapshot fingerprint. Changes if either changes."""
        return "ptl:" + self._wall.version

    def evaluate(self, action: Any) -> Any:
        """Check one bound action. DENY and UNRESOLVED stop it before the gatekeeper."""
        make = self._verdict_class or _harness_verdict_class()

        def out(label: str, reason: str, confirm: bool = False, missing: Iterable[str] = ()) -> Any:
            return make(label, reason, self.version, action.digest, action.state_version, confirm, tuple(missing))

        if action.policy_version != self.version:      # bound under other limits or another snapshot
            return out("DENY", "WALL_VERSION_CHANGED")
        try:
            args = json.loads(action.arguments_json)
        except (TypeError, ValueError):
            return out("UNRESOLVED", "MALFORMED_ARGS", missing=("MALFORMED_ARGS",))

        result = self._wall.evaluate(action.tool, args)
        decision = result.verdict.decision
        if decision is WallDecision.PASS:
            confirm = result.action is not None and result.action.capability in self._confirm
            return out("PASS", PASS_REASON, confirm)
        reason = ";".join(result.verdict.codes) or decision.value
        missing = result.verdict.codes if decision is WallDecision.UNKNOWN else ()
        return out(_HARNESS_LABEL[decision], reason, missing=missing)
