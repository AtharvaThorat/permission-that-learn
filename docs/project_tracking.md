# Project Tracking

## Fast-track prototype plan — October 31 and November 30

**Last reconciled:** 2026-10-20  
**Repository state:** `main`, local implementation integrated; no real-model
execution was performed during this reconciliation.

This tracker preserves the original plan but marks work only when supported by
the current code, CPU tests, configuration files, or recorded benchmark
evidence. CPU and synthetic validation are not treated as proof of real-model
utility, attack success, AgentDojo benchmark success, or Laya truncation
resolution.

## Status summary

| Task | Status | Verified evidence | Remaining work |
|---|---|---|---|
| 1. Freeze scope and environment | **Partially complete** | Pinned configuration profiles, AgentDojo revision metadata, CPU test environment, deterministic planning, and model endpoint profiles exist. | Validate a reproducible real runtime with the selected acting model, Laya assets, AgentDojo installation, and CARC/GPU or approved API access. |
| 2. One runner with two modes | **Complete for the implemented scope** | The shared runtime supports `unprotected`, `wall_only`, and `wall_gatekeeper`; CPU tests exercise mode-specific behavior and state isolation. | Run the same selected real task through the protected and unprotected paths. |
| 3. Real wall and Laya gatekeeper | **Partially complete** | The real `ptl.wall` adapter is integrated; wall decisions, gatekeeper paths, denials, pending approval, and stale evidence are CPU-tested. | Execute the Laya-backed path with real assets and verify an allowed action, blocked violation, and genuine approval wait in the target environment. |
| 4. First paired demonstration | **Not complete in the current platform** | Historical Colab pilot/result documents show limited earlier GPU execution; current synthetic evaluation tests verify paired identities and aggregation. | Run the planned small clean/attacked email/calendar comparison across unprotected and protected modes and publish a trace plus honest comparison table. |
| 5. Improve Laya and check Jev access | **Not started / deferred** | The existing Laya adapter and configuration seam are retained. No Jev adapter or shared real comparison is present. | Freeze the baseline first, then make development-only configuration changes. Add Jev only if access is approved; it must not block the demo. |
| 6. Approval memory and permission-creep tests | **Not implemented** | Current approval binding is scoped to pending actions and rechecked; this is not reusable approval memory. | Add explicit scoped JSON/SQLite memory, invalidation rules, reset behavior, and targeted changed-recipient/resource/task/policy tests. |
| 7. Controlled evaluation | **Planning infrastructure complete; evaluation not run** | Deterministic multi-model planning, bounded scheduling, retries/resume, result storage, aggregation, comparison, and replay are implemented and CPU-tested. | Freeze the real configuration, run matched unprotected/wall-only/wall+Laya trials, collect metrics, and report missing/failed/interrupted runs explicitly. |
| 8. Final demonstration and conclusions | **Not complete** | CLI, JSON/CSV artifacts, replay, and implementation reports exist. | Reproduce representative real runs, inspect artifacts, measure resource usage, update README/results, and document both benefits and failures. |

## Original plan, reconciled

### Task 1 — Freeze the scope and establish one working environment

**Status: Partially complete.**

The repository now has explicit experiment specifications and examples for
one-clean, three-mode, two-model sequential, two-model concurrent, and replay
workflows. Actor profiles include model IDs, endpoint information, resource
groups, and concurrency limits. The AgentDojo source revision is recorded in
the architecture/reference documentation.

The CPU environment is reproducible enough for the current tests:

```powershell
& '.\.venv-blackbox-tests\Scripts\python.exe' -m pytest -q -p no:cacheprovider
```

The latest verified result is **218 passed**.

The real environment is not frozen or verified. Required follow-up includes
selecting the first model, validating its endpoint/checkpoint and template,
resolving the AgentDojo/Laya dependency environment, confirming credentials and
assets, and running one real clean task.

### Task 2 — Build one runner with two execution modes

**Status: Complete for the implemented scope.**

The current implementation uses one shared runtime and explicit execution modes.
The supported experiment modes are:

- `unprotected`
- `wall_only`
- `wall_gatekeeper`

The scheduler and runtime preserve job identity, mode identity, state isolation,
and result lifecycle. The CPU suite covers mode selection and protected
execution behavior. A real paired task run remains necessary before claiming
the original demonstration deliverable.

### Task 3 — Connect a minimal real wall and the existing Laya gatekeeper

**Status: Partially complete.**

The real wall package is integrated through the `PtlWall` adapter. CPU tests
cover representative allow, ask/pending, and block behavior, including stale
state and policy evidence. Protected execution does not silently fall back to
the unprotected path.

The missing part is real-environment verification of the Laya-backed decision
path. The repository has not established that the required Laya runtime,
checkpoint, encoder assets, dependency combination, and context sizes work
for the target AgentDojo tasks. Historical benchmark evidence includes Laya
truncation and incomplete task outcomes; those results must not be presented as
a successful current demo.

### Task 4 — Produce the first paired demonstration

**Status: Not complete in the current platform.**

The evaluation package can plan matched jobs and aggregate their outputs. The
two-model sequential plan was verified as 24 deterministic jobs:

- 12 clean
- 12 attacked
- 8 `unprotected`
- 8 `wall_only`
- 8 `wall_gatekeeper`

This is planning evidence, not a paired real-model result. The October 31
deliverable still requires a small fixed task/attack selection, real execution,
three illustrative traces, and a comparison table containing task completion,
attack success, questions, execution time, and model/gatekeeper calls.

### Task 5 — Improve Laya and check Jev access

**Status: Not started and correctly deferred.**

The current work does not include model-weight fine-tuning, a Jev adapter, or a
Jev comparison. The correct order is to establish and freeze the baseline
first. Any Laya changes should be configuration or input-preparation changes
on development cases, with the original baseline retained.

### Task 6 — Add simple approval memory and permission-creep tests

**Status: Not implemented.**

The current approval machinery binds an approval to an exact pending action and
rechecks the wall. That is required safety behavior, but it is not approval
memory. No reusable scoped approval/rejection store should be claimed yet.

Future implementation must record at least task scope, effect, resource or
recipient, policy version, expiry, and approval count. Reuse must never bypass
wall denials, mandatory confirmation, contradictions, or missing evidence.

### Task 7 — Run a small controlled evaluation

**Status: Infrastructure complete; real evaluation outstanding.**

The evaluation package includes:

- deterministic planning
- multiple actors and modes
- bounded global, actor, and resource-group concurrency
- safe claims and leases
- retries and resume
- distinct attempt identities
- lifecycle-aware result storage
- JSON and CSV aggregation
- explicit earliest/latest attempt selection
- paired comparison identity checks
- offline replay using recorded permission evidence

The full CPU suite validates these behaviors. No current real evaluation has
been executed with the proposed 20 scenarios, two seeds, or up to 120 runs.
The real evaluation must be frozen before execution and must report incomplete,
failed, pending, and missing metrics rather than converting them to zeros.

### Task 8 — Package the final demonstration and conclusions

**Status: Not complete.**

The CLI and report structure are available, but the final demonstration needs
real representative runs, artifact inspection, resource measurements, and
evidence-based conclusions. The final report must separate:

- task completion
- attack success
- wall classification
- gatekeeper classification
- incorrect automatic allowances
- interruptions and failures
- approval-memory mistakes
- actor calls/tokens
- gatekeeper time/tokens
- latency
- GPU hours and peak memory
- API usage

Blocking all actions must not be presented as successful protection.

## Current implementation inventory

The following core surfaces are present and CPU-tested:

- `blackbox/`: actor, controller, contracts, wall/gatekeeper integration,
  execution, and audit behavior.
- `integrations/agentdojo/`: AgentDojo native pipeline, task/tool mapping,
  workspace facts, and runtime integration.
- `wall/`: real wall package, policy, context, harness, inventory, and tests.
- `experiment/`: specification, planning, runtime, scheduler, services,
  persistent storage, aggregation, comparison, estimation, replay, and CLI.
- `configs/experiments/`: one-clean, three-mode, two-model sequential,
  two-model concurrent, and replay configurations.
- `tests/blackbox/`, `tests/evaluation/`, and `wall/tests/`: CPU contract,
  integration, property, scheduler, storage, runtime, and replay coverage.

## Immediate next milestones

1. Select and document the first acting model and real execution environment.
2. Validate the combined AgentDojo, actor, Laya, and wall dependencies without
   changing policy semantics.
3. Run one clean AgentDojo task in `unprotected` mode.
4. Run the same task in `wall_only` and `wall_gatekeeper` modes using separately
   reset environments.
5. Inspect raw actor, wall, gatekeeper, tool, and result artifacts.
6. Run the small paired October demonstration.
7. Only after the baseline is stable, decide whether Jev or approval memory is
   needed for the November evaluation.

## Resource and scope guardrails

- Develop locally; use CARC or an explicitly approved API-backed endpoint for
  real model inference.
- Keep Laya and orchestration on CPUs where supported.
- Run GPU workloads sequentially on one GPU at a time unless a later resource
  review explicitly approves more.
- Keep the proposed 30 GPU-hour ceiling and reduce optional runs first.
- Do not download models, call external inference, or initialize Laya as part
  of CPU-only validation.
- Keep deferred work out of the prototype: large datasets, weight fine-tuning,
  30B–70B models, contextual bandits, broad architecture searches, production
  deployment, and comprehensive four-setup benchmarking.

## Bottom line

The shared pipeline and CPU-tested evaluation infrastructure are implemented.
The original prototype is **not fully complete** because the real environment,
real paired demonstration, approval memory, Jev comparison, controlled
real-model evaluation, and final evidence package remain outstanding.
