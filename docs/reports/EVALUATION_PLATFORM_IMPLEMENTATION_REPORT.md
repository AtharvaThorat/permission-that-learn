# Evaluation Platform Implementation Report

## Integration status

- Integration branch: `integration/evaluation-platform-20261020`
- Implementation commit: `f4697fb`
- Local `main`: fast-forwarded to the integration tip after verification.
- Nothing has been pushed.

## Implemented surface

The integration includes:

- The real `ptl.wall` package and `PtlWall` black-box adapter.
- Black-box modes: `unprotected`, `wall_only`, and `wall_gatekeeper`.
- AgentDojo pipeline wiring and CPU-safe actor/runtime controls.
- Experiment specifications, deterministic job planning, run storage, leases,
  bounded scheduling, retries/resume, runtime services, aggregation, paired
  comparison, estimation, and offline replay.
- CSV/JSON result and aggregate artifacts with distinct attempt and lifecycle
  identities.

## Verification

CPU-only command:

```powershell
& '.\.venv-blackbox-tests\Scripts\python.exe' -m pytest -q -p no:cacheprovider
```

Result: **218 passed** in 18.03 seconds. The suite includes 14 evaluation
platform tests and the existing black-box/wall tests.

Deterministic planning:

```powershell
& '.\.venv-blackbox-tests\Scripts\python.exe' -m experiment plan `
  --config configs/experiments/two-models-sequential.json
```

Result: 24 jobs (12 clean, 12 attacked), with 8 jobs in each supported mode.

## Supported commands

Validate or plan without model execution:

```powershell
& '.\.venv-blackbox-tests\Scripts\python.exe' -m experiment validate --config <config.json>
& '.\.venv-blackbox-tests\Scripts\python.exe' -m experiment plan --config <config.json>
```

Run or resume only with explicitly provisioned endpoints/assets:

```powershell
& '.\.venv-blackbox-tests\Scripts\python.exe' -m experiment run `
  --config <config.json> --output results/experiments --allow-models
& '.\.venv-blackbox-tests\Scripts\python.exe' -m experiment resume `
  --run-dir <run-dir> --allow-models
```

Aggregate, compare, and replay:

```powershell
& '.\.venv-blackbox-tests\Scripts\python.exe' -m experiment aggregate --run-dir <run-dir>
& '.\.venv-blackbox-tests\Scripts\python.exe' -m experiment compare --run-dirs <run-a> <run-b>
& '.\.venv-blackbox-tests\Scripts\python.exe' -m experiment replay `
  --source-run <run-dir> --config configs/experiments/replay-rules.json
```

Offline replay uses recorded permission evidence, does not call the acting
model or execute tools, preserves the source artifacts, and labels output as
offline action-decision evaluation.

## Limitations and next requirements

The current verification is synthetic and CPU-only. It does **not** establish
real-model utility, attack success, or resolution of Laya truncation problems.
Real experiments still require validated model endpoints, credentials, Laya
runtime and encoder assets, GPU scheduling, and a pilot review of recorded
artifacts before scaling.
