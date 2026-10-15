# AgentDojo guarded agent black box

This branch prepares an inference and evaluation pipeline for AgentDojo's `workspace` suite. The actor proposes tool calls; the black box validates them, checks a deterministic reference wall, optionally asks the existing Laya gatekeeper, and dispatches only authorized calls through the native AgentDojo runtime. The user reported 68 CPU tests passing on Windows Python 3.12.10. Model inference and benchmark episodes remain unverified.

For Google Colab, follow the [Colab runbook](docs/COLAB_RUNBOOK.md). The helper installs isolated environments, downloads pinned model assets, and can run one selected task with a 4-bit actor profile. Colab GPU execution has not yet been validated.

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
| `docs/` | Architecture, contracts, pinned compatibility evidence, implementation report, and runbook. |
| `requirements-blackbox.txt`, `requirements-blackbox-test.txt` | Proposed full-runtime and lightweight test dependencies. `requirements-lock.txt` retains the Laya stack. |

The four modes are `unprotected`, `wall_only`, `wall_gatekeeper`, and `wall_rules`. `wall_gatekeeper` is the Laya path; the others are explicit comparators. The reference wall is not the teammate's authoritative policy. No training or approval learning is implemented.

## Next steps

1. Read the [code map](docs/CODE_MAP.md), [runbook](docs/BLACKBOX_RUNBOOK.md), and [implementation report](docs/BLACKBOX_IMPLEMENTATION_REPORT.md). The [architecture](docs/BLACKBOX_ARCHITECTURE.md) and [contracts](docs/BLACKBOX_CONTRACTS.md) explain the boundaries; [compatibility notes](docs/AGENTDOJO_COMPATIBILITY.md) record the inspected AgentDojo revision.
2. Choose a compatible Python environment and install the proposed dependencies with `scripts/setup_blackbox.ps1`. Resolve any actual dependency conflict before proceeding; this combination has not been installed or tested here.
3. Provide local Qwen actor assets/server details and the existing Laya checkpoint cache. Copy `configs/blackbox/wall_gatekeeper.json` to an ignored `experiment.local.json`; fill in one real task ID and review the policy and workspace metadata. The runbook has the exact fields and commands.
4. Run `& $Python scripts/static_blackbox_review.py`, then the offline `& $BBPython -m blackbox.cli preflight --config configs/blackbox/experiment.local.json`. After setup and execution are authorized, run `& $BBPython -m pytest tests/blackbox -q` and one explicitly selected clean AgentDojo task. Compare protected and comparator modes only after that baseline works.

No model assets are included. The runbook's actor-server and native benchmark commands are future execution steps, not results from this branch.
