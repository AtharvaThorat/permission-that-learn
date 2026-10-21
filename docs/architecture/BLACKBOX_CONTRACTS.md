# Contracts and enforcement

Status: **IMPLEMENTED; behavior NOT RUN**.

| Contract | Meaning |
|---|---|
| `Config` | Strict JSON schema; unknown keys, learning, downloads, unsupported providers and invalid budgets rejected |
| `Episode` | Authentic task, provenance, opaque run/episode/attempt/environment IDs, policy identity, monotonic deadlines, counters and terminal state |
| `Proposal` | Native/model call ID, original ID, tool, original parsed JSON arguments |
| `BoundAction` | Immutable canonical original/execution JSON, digest, effects, facts, evidence completeness, schema/policy/state bindings |
| `WallVerdict` | PASS / DENY / UNRESOLVED, reason, binding, missing facts and separate confirmation metadata |
| `GateDecision` | Final ALLOW/ASK/BLOCK, separate raw recommendation/probabilities, backend/checkpoint/prompt provenance, error category and unknown calibration |
| `Binding` | Exact episode/attempt/action/schema/policy/state/expiry tuple |
| `AuthorizationLedger` | Private opaque references, single-use consumption and completed-attempt outcomes; no model-supplied tokens |
| `PendingApproval`, `ApprovalEvent` | Exact action snapshot and binding; trusted provider's matching approval/rejection |
| `Outcome` | Actual dispatch boolean, result/error, decision/reason and terminal status |
| `RunManifest` | Repository/config/package/model/policy/task/attack/budget/platform provenance and unresolved limitations |

Canonical JSON uses sorted object keys, UTF-8 text, compact separators and finite
JSON values. Array order, text case, whitespace inside text, numeric types, explicit
null versus absent keys are preserved. Duplicate input JSON keys are rejected.
Schema defaults/coercions are authorized in their normalized form; strings are not
heuristically interpreted as Python lists. Digests identify values, not authority.

| Condition | Enforcement |
|---|---|
| Unknown tool/schema/effects, nested executable, missing identity | Explicit error before native dispatch |
| Wall DENY / UNRESOLVED | Stop before semantic inference |
| Semantic BLOCK | Deny; cancel remainder of batch |
| Mandatory confirmation or incomplete evidence | Explicit ASK override unless semantic BLOCK already applies |
| Backend unavailable/timeout/malformed result | ASK; no automatic ALLOW |
| Semantic ALLOW | Issue private authorization; executor rechecks current state |
| ASK without trusted feedback | Terminal pending, zero dispatch of pending/later calls |
| Exact trusted approval | Recheck binding, wall, policy, resource state and expiry |
| Stale policy/state/schema/action | Invalidate attempt; actor may submit a freshly evaluated proposal |
| Native error or elapsed tool timeout | Preserve actual dispatch record; uncertain terminal; no retry |
| Audit failure | No dispatch if before call; preserve completed/uncertain state if after |

Principal fixed categories include `INVALID_ACTION`, `FORBIDDEN_EFFECT`,
`MISSING_FACTS`, `MISSING_LABEL`, `RECIPIENT_OUTSIDE_POLICY`,
`RESOURCE_OUTSIDE_SCOPE`, `RESOURCE_SENSITIVITY`, `MODEL_UNAVAILABLE`,
`INCOMPLETE_EVIDENCE`, `CONFIRMATION_REQUIRED`, `INVALID_APPROVAL`,
`APPROVAL_REJECTED`, `AUTHORIZATION_REJECTED`, `REDELIVERY_BINDING_MISMATCH`,
`BATCH_CANCELLED`, `TOOL_ERROR`, `TOOL_EXCEPTION_UNCERTAIN`,
`TOOL_TIMEOUT_UNCERTAIN`, `POST_DISPATCH_AUDIT_FAILURE`, and budget/protocol errors.
Native tool error text remains in the tool transcript, not the default audit.

Terminals: `completed` means the actor returned final text; it does **not** mean the
task passed the official utility checker. Others are `pending_approval`,
`budget_exceeded`, `uncertain_execution`, and `infrastructure_error`.

The reference policy's address syntax is deliberately narrow: exact mailbox strings
or exact domain membership, no display-name parsing and no suffix/subdomain match.
Domain case normalizes only for identity comparison; execution arguments remain
unchanged. Labels and resource scopes are sidecar policy concepts, not native
AgentDojo ground truth. An empty recipient allowlist blocks all outgoing recipients;
an absent resource scope permits all identities for that kind, while an explicit
empty scope permits none. Missing labels block only when `require_labels=true`.

`wall_rules` is a coarse declared comparator: pure reads ALLOW, writes ASK. It does
not parse task semantics. `wall_only` retains confirmation rules but bypasses Laya.
The unprotected comparator bypasses the wall/gate explicitly and only in the
simulation-only configuration. There is no failure-triggered mode switch.

Metrics: native utility/security fields are preserved. Clean attack success is
null/not applicable. ASK rate divides ASK decisions (including subsequently
script-approved ones) by evaluated action attempts, including invalid and
wall-denied attempts. Cancellations are counted separately. Unauthorized automatic
allows, false blocks and executed wall violations remain null until independent
labels or trace review supply evidence. Permission phase timings are audit fields;
no performance numbers have been measured in this phase.
