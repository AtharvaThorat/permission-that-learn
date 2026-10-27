# Repository and documentation guide

Start with the [project overview](../README.md) and [development guidelines](PROJECT_GUIDELINES.md).
The [project tracker](project_tracking.md) records overall progress;
[weekly task documents](process_documentation/) define assignments and task-specific evidence.

## Repository structure

Paths below are relative to the repository root.

| Directory | Purpose |
|---|---|
| `.github/` | CI workflows, including wall-package checks. |
| `blackbox/` | Actor clients, action validation, permission mediation, execution, audit, and configuration. |
| `gatekeeper/` | Laya checkpoint configuration, prompts, worker lifecycle, and decision policy. |
| `wall/` | Standalone `ptl.wall` package, policies, and existing package tests in `wall/tests/`. |
| `integrations/agentdojo/` | Benchmark pipeline, tool/message mappings, workspace facts, and runners. |
| `experiment/` | Planning, scheduling, runtime services, artifacts, aggregation, comparison, replay, and CLI. |
| `configs/` | Actor, policy, attack, and experiment configurations, including frozen and panel-15 profiles. |
| `tests/` | Repository regression tests; `blackbox/` covers runtime contracts and `evaluation/` covers experiments. |
| `notebooks/` | All testing, setup-validation, baseline, and protected-run notebooks. |
| `scripts/` | Setup, serving, validation, benchmark, and analysis utilities. |
| `handoff/` | Execution commands and environment/validation metadata; check provenance before reuse. |
| `docs/` | Guidelines, tracker, task plans, architecture, operations, and evidence described below. |
| `results/` | Generated experiment artifacts, not source code or new documentation. |
| `tmp/` | Ignored temporary work and scratch artifacts. |
| `.venv/`, `.venv-blackbox-tests/` | Local Python environments, not portable project assets. |
| `.hypothesis/`, `.pytest_cache/`, `__pycache__/` | Generated test/Python caches; do not commit their contents. |

## Root files

| File | Purpose |
|---|---|
| [README.md](../README.md) | Project purpose, capabilities, status, and entry points. |
| [SETUP_HANDOFF.md](../SETUP_HANDOFF.md) | Actor setup and baseline/protected smoke-test handoff. |
| [pyproject.toml](../pyproject.toml) | Package metadata, dependencies, and experiment CLI entry point. |
| [pytest.ini](../pytest.ini), [conftest.py](../conftest.py) | Test discovery and default network/model safeguards. |
| [requirements.txt](../requirements.txt), [requirements-lock.txt](../requirements-lock.txt) | Laya runtime dependency specifications and pinned environment. |
| [requirements-blackbox.txt](../requirements-blackbox.txt) | Combined black-box runtime dependency specification. |
| [requirements-test.txt](../requirements-test.txt) | Minimal test dependencies. |
| [requirements-blackbox-test.txt](../requirements-blackbox-test.txt) | CPU runtime tests with pinned AgentDojo. |
| [requirements-evaluation-test.txt](../requirements-evaluation-test.txt) | Evaluation tests, local wall package, and property-test dependencies. |
| [.env.example](../.env.example) | Environment-variable template; never store credentials in tracked files. |
| [.gitignore](../.gitignore), [.gitattributes](../.gitattributes) | Local-file exclusions and Git file-handling rules. |

Reuse these files; do not add duplicate root-level reports or dependency manifests.

## Documentation map

| Location | Contents |
|---|---|
| [PROJECT_GUIDELINES.md](PROJECT_GUIDELINES.md) | Coding, branching, testing, documentation, and PR rules. |
| [project_tracking.md](project_tracking.md) | Concise completed work, remaining work, and blockers. |
| [process_documentation/](process_documentation/) | Weekly task plans and task-specific progress/evidence. |
| [architecture/](architecture/) | Code map, runtime design, contracts, and AgentDojo compatibility/source inspection. |
| [operations/](operations/) | Setup, execution, Colab, benchmark, and injection runbooks. |
| [user_manual/](user_manual/) | User-facing machine setup and execution commands for Linux/CARC. |
| [user_manual/colab_cli_quick_commands.md](user_manual/colab_cli_quick_commands.md) | Pinned two-model setup, Laya probes, three-suite native smoke/panel commands, live approvals and export. |
| [reports/](reports/) | Implementation, readiness, protected-smoke, and dated progress reports. |
| [benchmark-results/](benchmark-results/) | Historical Colab results, not current execution instructions. |
| [schemas/](schemas/) | Machine-readable artifact schemas, including the run manifest. |

## Task plans and evidence

- [Week 1 tasks](process_documentation/week1-18-10-2026/week_1_tasks.md)
- [Week 2 tasks](process_documentation/week2-24-10-2026/week_2_tasks.md)
- [Siddharth Task 1 implementation completion](process_documentation/week2-24-10-2026/SIDDHARTH_TASK1_COMPLETION.md)
- [Environment validation report](process_documentation/week1-18-10-2026/permission_that_learn_environment_validation_report_2026-10-22.md)
- [Baseline and protected-run report](process_documentation/week1-18-10-2026/permission_that_learn_baseline_and_protected_runs_report_2026-10-24.md)

## Technical references

- [Linux/CARC setup and runs](user_manual/MACHINE_SETUP_AND_RUNS.md): clone,
  install, pinned model downloads, config generation, sequential/parallel models,
  conditional batch submission, resume and reports.

- Architecture: [code map](architecture/CODE_MAP.md), [runtime design](architecture/BLACKBOX_ARCHITECTURE.md), [contracts](architecture/BLACKBOX_CONTRACTS.md).
- Integration: [AgentDojo compatibility](architecture/AGENTDOJO_COMPATIBILITY.md), [source inspection](architecture/AGENTDOJO_SOURCE_INSPECTION.json), [run manifest schema](schemas/run_manifest.schema.json).
- Operations: [runtime runbook](operations/BLACKBOX_RUNBOOK.md), [Colab setup](operations/COLAB_RUNBOOK.md), [benchmark](operations/COLAB_BENCHMARK.md), [injection comparison](operations/COLAB_INJECTION_RUN.md).
- Small real functional checks, optional actor profiles and offline HTML reports:
  [tested T4 handoff](../SETUP_HANDOFF.md#functional-validation-2026-10-25).
- Implementation: [black-box report](reports/BLACKBOX_IMPLEMENTATION_REPORT.md), [evaluation platform report](reports/EVALUATION_PLATFORM_IMPLEMENTATION_REPORT.md).
- Progress: [protected smoke report](reports/PERSON3_PROTECTED_SMOKE_REPORT.md), [October 24 report](reports/PROJECT_PROGRESS_2026-10-24.md).
- Historical results: [Colab pilot](benchmark-results/COLAB_PILOT_RESULTS.md), [40-task run](benchmark-results/COLAB_40_TASK_RESULTS.md).

Reports describe code and runs at their recorded revision. Consult the tracker
and current task plan before treating historical evidence as current readiness.
