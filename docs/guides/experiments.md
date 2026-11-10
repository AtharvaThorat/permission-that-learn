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

## Laya fine-tuning data

`grids training-data` builds the Laya ALLOW/ASK/BLOCK dataset in
[`docs/results/laya-permission-v1/`](../results/laya-permission-v1/README.md) from
native AgentDojo actions, through the same replay path as frozen evaluation. Install
`environments/training-data.txt`, then run `fetch`, `candidates`, `review`, `finalize
--reviewer "<who>"` and `validate`. `candidates` refuses to run while that directory's
`review.csv` exists, because review decisions are keyed to candidate ids. Builds are
deterministic. These labels train the model; they are not independent evaluation labels
for the frozen-action comparison above.

For 1,024-token checkpoints such as `TextCortex/laya-cybersec`, set the gatekeeper `input_profile`
to `compact_v1` and `max_input_tokens` to 1024. `compact`, `compact-tokens` (in a `environments/laya.txt`
environment) and `compact-validate` build and check
[`docs/results/laya-permission-v1-compact/`](../results/laya-permission-v1-compact/README.md) with the
same function.

## Approval memory

`grids memory simulate --seeds 50 --passes 3 --output results/memory-sim/<run>` replays the 450 dataset actions as
per-suite streams through the four setups (no protection, fixed rules, learning without the Wall, learning inside
the Wall) with careful and careless simulated users. It needs no model and writes `runs.csv`, `summary.csv`,
`curves.csv` and `run.json`. See [memory-sim](../results/memory-sim/README.md).

For live runs, add a `learning` block to a run specification, for example
`"learning": {"enabled": true, "learner": "counting", "granularity": "exact", "approvals_to_allow": 2}`. One memory
is shared by the run's `wall_gatekeeper` episodes. It answers only `NEEDS_CLARIFICATION` and `UNCERTAIN` asks, after
a Wall PASS. Each episode records `memory.jsonl` and `memory-policy.json`. Disabled specifications keep their
identities.

### Grants versus counting on laya-pairs-v1

Download `data/laya-pairs-v1.jsonl` and `metadata/laya-pairs-v1.json` from the gated
`siddharth-magesh/grids-laya-permission-v1` into ignored `tmp/`. In a `environments/laya.txt` environment,
`grids permissions laya-predict --pairs <pairs> --metadata <metadata> --output <file>` records Laya-Cybersec
decisions (CPU is enough). `grids permissions simulate --pairs <pairs> --output results/permission-memory/<run>`
then compares no memory, counting and grants with and without the Wall; it checks the pairs hash against the
recorded predictions. See [permission-memory](../results/permission-memory/README.md). For live runs,
`"learner": "grants"` answers judgment asks only under user-issued grants; the file operator channel logs offers
but cannot issue grants.
