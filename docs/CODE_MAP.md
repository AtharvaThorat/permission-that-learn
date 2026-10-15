# Code map for this branch

The guarded path is: AgentDojo supplies a task and tool runtime → the actor proposes a call → the controller freezes and checks it → the reference wall and selected gate decide → the executor rechecks the authorization and calls the supplied native tool → the result returns to the actor. No benchmark episode or model has been run in this branch.

| File | Role |
|---|---|
| `blackbox/__init__.py`, `factory.py` | Public `build_agentdojo_pipeline` entry point and lazy pipeline construction. |
| `blackbox/config.py` | Strict actor, gate, wall, benchmark, audit, and runtime settings; JSON loader. |
| `blackbox/contracts.py` | Proposal, frozen action, wall verdict, gate decision, outcome, and dependency interfaces. |
| `blackbox/actions.py` | JSON validation, canonical serialization/digests, native-schema normalization, and action binding. |
| `blackbox/state.py` | Clock and per-episode identity, limits, counters, and terminal state. |
| `blackbox/controller.py` | Actor loop; sequential proposal validation, permission decisions, approval handling, and results. |
| `blackbox/execution.py` | Single `runtime.run_function` site; checks and consumes authorization before native dispatch. |
| `blackbox/audit.py` | Redacted JSONL or in-memory audit events and write-failure handling. |
| `blackbox/manifest.py` | Run provenance: source, config, versions, model/policy identities, and limits. |
| `blackbox/cli.py` | Offline `inspect-config` and `preflight`; neither runs a task or probes an endpoint. |
| `blackbox/actors/base.py` | Actor interface. |
| `blackbox/actors/openai_compatible.py` | Explicit OpenAI-compatible HTTP actor with tool-call parsing and request limits. |
| `blackbox/actors/scripted.py` | Scripted actor for synthetic tests. |
| `blackbox/permissions/wall.py` | Reference deterministic policy for effects, recipients, resource scopes, and labels. |
| `blackbox/permissions/facts.py` | Interface for resolving trusted action/resource facts. |
| `blackbox/permissions/gatekeeper_adapter.py` | Adapter to the existing Laya gate and native tool schemas. |
| `blackbox/permissions/rules.py` | Simple read/write comparator gate for the separate `wall_rules` mode. |
| `blackbox/permissions/bindings.py` | Action/policy/state/expiry binding and single-use authorization ledger. |
| `blackbox/permissions/approvals.py` | Pending approvals and trusted scripted approval provider; no approval learning. |
| `integrations/agentdojo/pipeline.py` | AgentDojo pipeline interface and mode-specific wiring. |
| `integrations/agentdojo/codec.py` | Native message, function-call, and tool-result translation. |
| `integrations/agentdojo/tools.py` | Native tool registry and Pydantic parameter schemas. |
| `integrations/agentdojo/context.py` | Workspace resource facts and provenance-labeled metadata. |
| `integrations/agentdojo/runner.py` | Explicit selected-task benchmark runner and native score recording. |
| `gatekeeper/config.py`, `model_manifest.json` | Pinned Laya checkpoint selection and revision metadata. |
| `gatekeeper/schemas.py`, `validation.py` | Gate request/output schemas and legacy default request validation. |
| `gatekeeper/questions.py`, `state.py` | Existing prompt/question logic and model input state. |
| `gatekeeper/laya_adapter.py` | Existing persistent Laya worker, response parsing, and lifecycle. |
| `gatekeeper/policy.py` | Existing deterministic ALLOW/ASK/BLOCK policy; optional validator seam for native tools. |
| `configs/blackbox/*.json` | Explicit modes and example settings; policies and metadata live under `policies/`. |
| `tests/blackbox/` | Synthetic acceptance, native contract, enforcement, transport, config, fact, and Colab orchestration tests. The user reported 68 original tests passing; seven new helper tests passed locally. |
| `scripts/colab_blackbox.py` | Linux/Colab dependency setup, asset download, CPU tests, and one-task GPU trial with server cleanup. |
| `scripts/static_blackbox_review.py` | Source-only AST/JSON/diff checks, with no application imports. |
| `scripts/setup_blackbox.ps1`, `serve_blackbox_actor.sh` | Future dependency setup and actor-server launch, respectively. |

The old root-level `tests/test_*.py`, standalone `gatekeeper/__main__.py`, prototype evaluation scripts, fixtures, and benchmark snapshots were removed at the user's request. They are still present in the earlier Laya commit. The retained `gatekeeper/` runtime is a required dependency of `wall_gatekeeper`.

For actual setup and the order of future checks, see [the runbook](BLACKBOX_RUNBOOK.md). For trust boundaries and known limits, see [the architecture](BLACKBOX_ARCHITECTURE.md) and [contracts](BLACKBOX_CONTRACTS.md).
