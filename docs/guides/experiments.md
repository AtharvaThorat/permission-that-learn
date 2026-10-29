# Collection, frozen evaluation, and reporting

Complete [setup and small functional checks](setup.md) before collecting data.
`benchmark config` accepts repeated `--profile`, `--task`, `--seed`, and `--mode`,
plus `--suite`, `--repetitions`, `--all-tasks`, `--native-attack`, `--objective` /
`--all-objectives`, `--clean-only` / `--attacked-only`, and `--parallel`.
Omitting either selection flag retains both selected clean tasks and attacks.
Use `--help` and discovery rather than editing source to select native tasks.

One spec targets one suite. Generate a config for each of Workspace, Slack and
Banking. A single-GPU run serves one model phase at a time (`run --actors <profile>`;
then start the next server and `resume --actors <profile>`). Parallel configs use
distinct ports and resource caps but **do not** allocate hardware or start servers.

## Freeze the collection and evaluate identical actions

Use fresh output names; existing datasets, evaluations and reports are not overwritten.

```bash
python -m grids dataset capture --run-dir results/smoke/<run-id> --output results/datasets/actions-01
python -m grids dataset validate --dataset results/datasets/actions-01
python -m grids dataset export-labels --dataset results/datasets/actions-01 --output results/labels-01.template.json

# Use the Laya runner with offline variables from setup. Configure cache_dir in
# a personal copy of configs/experiments/authorization.json if HF_HOME differs.
"$RUN_PY" -m grids evaluate --dataset results/datasets/actions-01 \
  --config configs/experiments/authorization.json --output results/evaluations/decisions-01 --allow-models
"$RUN_PY" -m grids report --dataset results/datasets/actions-01 \
  --evaluation results/evaluations/decisions-01 --output results/reports/unlabeled-01
```

Repeat `--run-dir` to pool explicitly selected source attempts. Capture includes all
attempts supplied, including cancelled and invalid proposals; it does not pick a
best retry. Sources predating decision-time capture are rejected: recollect them.
For a CPU Wall-only check, copy the evaluation config and set `comparators` to
`["wall_only"]`; omit `--allow-models`.

After independent annotation under the [label contract](../architecture/authorization/contract.md):

```bash
python -m grids dataset import-labels --dataset results/datasets/actions-01 \
  --labels results/labels-01.reviewed.json --output results/labels-01.accepted.json
python -m grids report --dataset results/datasets/actions-01 \
  --evaluation results/evaluations/decisions-01 --labels results/labels-01.accepted.json \
  --output results/reports/reviewed-01
```

Open the output `report.html`. `summary.json`, `metrics.csv` and `decisions.csv`
include paired accuracy/coverage and an action review. `actions.json` contains the
full frozen source; evaluation `decisions.jsonl` contains binding, permission input,
raw predictions and errors. Keep datasets, label versions and evaluation artifacts
together when exporting. Checksums detect corruption, not malicious data authorship.

## Live approval and recovery

`benchmark run --approval-dir <trusted-dir> --approval-wait-seconds 60` enables a
bounded live wait. Use `benchmark approval --pending <pending.json> --decision
approve` (or `reject`) from a trusted operator. Default unresolved ASK becomes
`pending_approval` without blocking other episodes. The exact live binding must
still be valid; after process exit no suspended action can be resumed.

`benchmark resume --run-dir <run> --allow-models` schedules unfinished work.
`--retry-status infrastructure_error` creates new attempts, not action continuation.
Use `benchmark aggregate --run-dir <run>` and `report --run-dir <run>` for native
secondary scores. Full-suite commands (`--all-tasks --all-objectives`) are for reviewed
benchmark campaigns after smoke validation and resource budgeting, not initial tests.
