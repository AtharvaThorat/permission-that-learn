# Research documentation

The [project overview](../README.md) describes the contribution and links the
[manuscript](../paper/manuscript.pdf). This index is the entry point for detailed documentation.

## Run and integrate

- [Reproduce the pipeline](guides/reproduce.md): local simulated demonstration, real Laya check, saved results and validation.
- [Machine setup](guides/setup.md): environments, model assets, Colab and serving.
- [Experiments](guides/experiments.md): native AgentDojo, identical-action replay, grants and contextual learning.
- [Application integration](guides/integration.md): use the shared controller in another application.
- [Actor profiles](guides/models.md) and [CARC execution](guides/carc.md).

## Architecture and evaluation

- [System](architecture/system/overview.md), [pipeline diagram](architecture/system/pipeline.png).
- [Authorization contract](architecture/authorization/contract.md): trusted evidence and exact execution binding.
- [Evaluation method](architecture/evaluation/method.md): paired observations and metric definitions.
- [Permission-memory research](architecture/authorization/permission-memory.md): historical designs and comparisons;
  current production behavior is described in the experiment guide.

## Evidence and research history

- [Results index](results/README.md): curated data, historical studies and current aggregate release.
- [Release evidence](results/research-release/README.md): downloadable HTML, CSV, JSON and provenance.
- [Permission-learning milestone](milestones/2026-11-permission-memory.md): actual checks and limitations.
- Historical milestones: [refactor](milestones/2026-10-refactor.md),
  [dataset](milestones/2026-11-laya-training-data.md), [compact contexts](milestones/2026-11-laya-compact.md),
  [approval-memory study](milestones/2026-11-approval-memory.md).

## Maintain the project

- [PROJECT_GUIDELINES](PROJECT_GUIDELINES.md): contributor and coding-agent instructions.
- [Project tracking](project_tracking.md): progress and remaining work.
- [Test catalog](development/testing.md): retained security and integrity checks.

`src/grids/` holds the reusable pipeline; `experiments/notebooks/` contains thin walkthroughs;
`configs/` and `environments/` hold reproducible settings. Ignored `results/`, `workspace/` and
`tmp/` hold local generated data and assets. Do not duplicate them into source or documentation.
