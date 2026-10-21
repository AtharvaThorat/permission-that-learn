# AgentDojo guarded agent black box

This branch provides an inference and evaluation pipeline for AgentDojo's `workspace` suite. The actor proposes tool calls; the black box validates them, checks a deterministic reference wall, optionally asks the existing Laya gatekeeper, and dispatches only authorized calls through the native AgentDojo runtime. The current CPU suite has 97 passing tests, including native injection scoring with scripted actors.

For Google Colab, follow the [Colab runbook](docs/operations/COLAB_RUNBOOK.md). Recorded T4 runs verified model loading, decisions and some tool executions, but no official task successes. The 40-task clean run also exposed email/file collection truncation; the adapter now summarizes those collections for Laya while retaining full wall/freshness evidence.

For a timed five-task trial with a shareable report, use the [quick benchmark instructions](docs/operations/COLAB_BENCHMARK.md) or `notebooks/colab_quick_benchmark.ipynb`. This keeps the Qwen actor, original Laya gatekeeper, and reference wall; setup fixes come from the supplied Colab execution notebook.

For explicit prompt injections, use the [injection comparison instructions](docs/operations/COLAB_INJECTION_RUN.md): five native task/attack cases, clean and injected, across three modes (30 episodes). The new GPU comparison has not yet been run; CPU tests validate placement, exposure tracking and native scoring.

The Laya runtime under `gatekeeper/` is intentionally retained because `wall_gatekeeper` mode calls it. The old standalone Laya CLI, synthetic fixture set, benchmark snapshots, and evaluation scripts/tests have been removed from this branch's working tree. They remain recoverable from the earlier Git commit/branch. No other branch was edited. This branch still descends from `feature/laya-gatekeeper`; file cleanup does not rewrite Git history.

## Code map

| Area | What it contains |
|---|---|
| `blackbox/actors/` | Acting model client (`openai_compatible.py`) and a scripted test actor. |
| `blackbox/actions.py`, `contracts.py`, `config.py`, `state.py` | Canonical action data, interfaces, strict configuration, and per-episode state. |
| `blackbox/controller.py` | Actor turn loop and tool-call mediation. |
| `blackbox/permissions/` | Reference wall, workspace facts, approval/binding rules, and the adapter to Laya. |
| `blackbox/execution.py` | Single native tool-dispatch boundary with authorization rechecks. |
| `blackbox/audit.py`, `manifest.py` | Redacted event trail and run provenance. |
| `blackbox/factory.py`, `cli.py` | Public pipeline factory and offline configuration/preflight commands. |
| `integrations/agentdojo/` | Native message/tool codec, workspace fact mapping, pipeline interface, and benchmark runner. |
| `gatekeeper/` | Reused Laya model configuration, prompts, worker lifecycle, validation, and decision policy. `policy.py` adds a validator seam for native AgentDojo tools. |
| `configs/blackbox/` | Example modes, reference wall policy, metadata, and actor-server setup notes. Copy an example to an ignored `*.local.json` before use. |
| `tests/blackbox/` | Synthetic acceptance and contract tests (68 user-reported passes), plus seven locally passing Colab helper tests. |
| `scripts/` | Future setup/actor-server scripts and a source-only static checker. |
| `docs/` | Documentation index with architecture, operations, reports, results, and reference evidence. |
| `requirements-blackbox.txt`, `requirements-blackbox-test.txt` | Proposed full-runtime and lightweight test dependencies. `requirements-lock.txt` retains the Laya stack. |

The four modes are `unprotected`, `wall_only`, `wall_gatekeeper`, and `wall_rules`. `wall_gatekeeper` is the Laya path; the others are explicit comparators. The reference wall is not the teammate's authoritative policy. No training or approval learning is implemented.

## Next steps

1. Read the [documentation index](docs/README.md) and [project development guidelines](docs/PROJECT_GUIDELINES.md) before contributing. Then read the [code map](docs/architecture/CODE_MAP.md), [runbook](docs/operations/BLACKBOX_RUNBOOK.md), and [implementation report](docs/reports/BLACKBOX_IMPLEMENTATION_REPORT.md). The [architecture](docs/architecture/BLACKBOX_ARCHITECTURE.md) and [contracts](docs/architecture/BLACKBOX_CONTRACTS.md) explain the boundaries; [compatibility notes](docs/architecture/AGENTDOJO_COMPATIBILITY.md) record the inspected AgentDojo revision.
2. Choose a compatible Python environment and install the proposed dependencies with `scripts/setup_blackbox.ps1`. Resolve any actual dependency conflict before proceeding; this combination has not been installed or tested here.
3. Provide local Qwen actor assets/server details and the existing Laya checkpoint cache. Copy `configs/blackbox/wall_gatekeeper.json` to an ignored `experiment.local.json`; fill in one real task ID and review the policy and workspace metadata. The runbook has the exact fields and commands.
4. Run `& $Python scripts/static_blackbox_review.py`, then the offline `& $BBPython -m blackbox.cli preflight --config configs/blackbox/experiment.local.json`. After setup and execution are authorized, run `& $BBPython -m pytest tests/blackbox -q` and one explicitly selected clean AgentDojo task. Compare protected and comparator modes only after that baseline works.

No model assets are included. The runbook's actor-server and native benchmark commands are future execution steps, not results from this branch.
