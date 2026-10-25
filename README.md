# GRIDS: Permissions That Learn

GRIDS is a research platform for evaluating permission enforcement around
tool-using language-model agents. It integrates AgentDojo's workspace benchmark,
a deterministic permission wall, and the Laya semantic gatekeeper to compare
task completion and prompt-injection outcomes under matched conditions.

## How it works

An acting model proposes a tool call. The runtime validates the call, binds it
to the current workspace state, applies permission checks, and dispatches only
authorized actions through AgentDojo. Actions awaiting approval remain pending;
gatekeeper failures do not silently bypass protection.

| Evaluation mode | Permission checks |
|---|---|
| `unprotected` | Explicit comparator without wall or gatekeeper checks. |
| `wall_only` | The integrated `ptl.wall` enforces deterministic policy. |
| `wall_gatekeeper` | The wall checks policy, then Laya evaluates semantic intent with ALLOW, ASK, or BLOCK decisions. |

The experiment platform supports deterministic planning, bounded scheduling,
resume/retry handling, distinct attempt artifacts, JSON/CSV aggregation, paired
comparisons, and offline action-decision replay. `wall_rules` is an additional
legacy comparator in the black-box runtime.

## Current scope

The runtime, wall integration, Laya adapter, and evaluation infrastructure are
implemented. A real unprotected panel-15 run is recorded; matched protected
panel runs and a successful integrated real-Laya rerun remain outstanding.
Snapshot-layout and initialization-error reporting fixes are implemented and
CPU-tested. Approval memory and permission learning are not yet implemented.

CPU tests establish software behavior, not real-model utility, attack resistance,
or resolution of Laya truncation issues. See the [project tracker](docs/project_tracking.md)
for completed work, blockers, and next steps, and the
[weekly task documents](docs/process_documentation/) for assignments and evidence.

## Getting started

Use a dedicated CPU test environment to validate the platform without model
downloads or inference. Run from the repository root with that environment active:

```sh
python -m pip install -r requirements-evaluation-test.txt
python -m pytest -q -p no:cacheprovider
python -m experiment plan --config configs/experiments/frozen/unprotected.json
python -m experiment --help
```

Real experiments require a configured actor endpoint, pinned local Laya assets
for `wall_gatekeeper`, and compatible, separate actor-server and runner
environments. Follow the [runtime runbook](docs/operations/BLACKBOX_RUNBOOK.md)
and [smoke-test handoff](SETUP_HANDOFF.md) before execution. Testing and validation
notebooks live in [notebooks/](notebooks/); no model weights are included.

## Documentation and contributions

The [repository and documentation guide](docs/README.md) explains the directory
structure, key files, setup references, and available reports.

Before changing code, read the [project guidelines](docs/PROJECT_GUIDELINES.md)
and applicable weekly task plan. Pull the latest base, work on a focused branch,
validate the change, and update progress records. The repository owner creates
and merges the pull request; coding agents must not merge into `main` or push
without authorization.
