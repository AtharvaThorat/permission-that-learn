# Use GRIDS in an application

GRIDS is the authorization pipeline; an application or demonstration UI should call the existing
controller rather than reproduce its permission logic. The native AgentDojo integration is the
working reference adapter in `src/grids/benchmarks/agentdojo/`.

1. Implement the `Actor` interface in `src/grids/core/contracts.py`, or use the existing
   OpenAI-compatible client. Supply native tool schemas and preserve proposed arguments.
2. Resolve resources, recipients and effects from trusted application state using the facts
   interface. Tool output and actor text cannot establish user identity or permission.
3. Construct the existing `Controller` with the Wall, Laya gate, approval provider, executor and
   audit sink. Use `core/factory.py` and `runs/runtime.py` as the construction reference.
4. Route every proposed tool call through the controller. Dispatch only through `GuardedExecutor`;
   ASK withholds execution until an eligible explicit grant or exact human approval is validated.
5. Supply the operator-authenticated user ID to `ScopedApprovalProvider` and a persistent
   `PermissionStore`. Keep grant issuance separate from approval of one action.
6. Persist errors, pending approvals and uncertain executions. Restart does not resume an old
   pending invocation; no external side effect is automatically replayed.

This is a local research interface, not a hosted identity or authentication service. Applications
must provide authentication and trusted state/versioning. The SQLite store serializes grant
revocation with dispatch and may time out concurrent writers during long tool calls.

Laya ALLOW/BLOCK behavior, mandatory confirmation and the deterministic Wall stay outside learner
control. Offline free/pooled/counting comparisons in `grids learning` are not application providers.
See [architecture](../architecture/system/overview.md) and [permission commands](experiments.md).
