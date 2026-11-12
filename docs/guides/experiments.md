# Collection, frozen evaluation, and reporting

## Scoped permission learning (local research)

Learning can reuse an explicit permission but cannot create one. The trusted local operator
supplies the user identity; actor messages cannot choose it. Add this to an experiment specification
to enable shadow learning; use `active` only for an explicitly enabled experiment:

```json
"learning": {
  "enabled": true,
  "learner": "scoped",
  "user_id": "alice",
  "store_path": "results/permissions/alice.sqlite",
  "mode": "shadow",
  "frozen": false
}
```

Modes: `off` asks normally, `grants` reuses matching explicit grants, `shadow` records learner
recommendations while asking, and `active` lets the learner choose ASK or use a valid grant.
Unchanged ALLOW/BLOCK decisions bypass learning. Mandatory confirmation and model/evidence
failures cannot use grants. Old `counting`, `bandit`, and broad `grants` learners are simulation-only.

```bash
# Existing runner and trusted file approval channel
python -m grids benchmark run --config configs/experiments/my.local.json --output results/runs --allow-models --approval-dir results/approvals --approval-wait-seconds 120
# Grant and one-action approval are separate operations. Granting does not execute a pending action.
python -m grids permissions grant --store results/permissions/alice.sqlite --user alice --pending results/approvals/PENDING_ID.json --ttl-seconds 86400 --max-uses 5
# A one-action response still requires the original live process and fresh binding:
python -m grids benchmark approval --pending results/approvals/PENDING_ID.json --decision approve
python -m grids permissions list --store results/permissions/alice.sqlite --user alice
python -m grids permissions revoke --store results/permissions/alice.sqlite --user alice --grant-id GRANT_ID
# Reproduce constructed checks; output directory must be new
python -m grids permissions check --output results/permission-learning/check-01
# Use the existing Laya environment and cached assets (no downloads)
python -m grids permissions check --output results/permission-learning/laya-01 --real-laya --cache workspace/cache
# Regenerate CSV/HTML from saved evidence; no inference
python -m grids permissions report --run-dir results/permission-learning/laya-01
```

Open `report.html`; `actions.csv`/`actions.jsonl` contain decisions and full traces. `laya.csv`,
`laya.jsonl`, and `laya-summary.json` contain actual model outputs when requested. `run.json`
records packages, revision, latency, CPU time, and sampled process-tree RSS (requires optional
`psutil`; missing measurements remain null). These are constructed cases, not native benchmark scores.

Review `memory.jsonl` or the local SQLite decision record before submitting feedback. A review JSON is:

```json
{
  "decision_id": "DECISION_ID", "feedback_id": "UNIQUE_REVIEW_ID",
  "reviewer": "human-reviewer", "rationale": "Checked request, policy, evidence and recorded outcome",
  "preference": "acceptable", "authorization_label": "ALLOW",
  "consent": true, "suitable": true,
  "verified": {"request": true, "policy": true, "outcome": true}
}
```

```bash
python -m grids permissions review --store results/permissions/alice.sqlite --user alice --file results/review.json
python -m grids permissions export --store results/permissions/alice.sqlite --user alice --output results/reviewed-training.jsonl
```

Preference may be `acceptable`, `unwanted`, or null; authorization label may be ALLOW/ASK/BLOCK
or null. Unresolved examples must not be marked suitable. Failed/uncertain outcomes cannot be
exported for training. Approval/rejection never automatically supplies an authorization label.
Export requires consent and explicit verification; private traces and databases stay local.

Grants bind the full action, original request, trusted facts, schema and policy. Changing any
of these requires a new grant. Rejection or unwanted-use review revokes matching grants.
Expiry uses UTC epoch time, not consultation counts. Reservations consume uses conservatively,
including failed or uncertain attempts. Restart preserves grants and learner state, but old
reservations/pending actions cannot dispatch. SQLite serializes grant dispatch with revocation;
long tool calls can cause other writers to fail closed after a five-second lock wait.

The learner uses epsilon 0.1, seed 42, ten initial eligible observations, bounded contextual
features, and learning rate 0.05. ASK costs 1; reviewed acceptable/unwanted reuse costs 0/10.
Unobserved reuse gets no reward. `frozen: true` prevents learner/RNG updates during holdout.
This release does not train or promote Laya checkpoints.

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

Historical counting/broad-grant modes are simulation-only. Live runs require the scoped
configuration above; repeated approvals never create authority.

### Grants versus counting on laya-pairs-v1

Download `data/laya-pairs-v1.jsonl` and `metadata/laya-pairs-v1.json` from the gated
`siddharth-magesh/grids-laya-permission-v1` into ignored `tmp/`. In a `environments/laya.txt` environment,
`grids permissions laya-predict --pairs <pairs> --metadata <metadata> --output <file>` records Laya-Cybersec
decisions (CPU is enough). `grids permissions simulate --pairs <pairs> --output results/permission-memory/<run>`
then compares no memory, counting and grants with and without the Wall; it checks the pairs hash against the
recorded predictions. See [permission-memory](../results/permission-memory/README.md). Live runs use the scoped grant commands above.

## Offline contextual-policy comparisons

Reuses Atharva's `feature/permission-learning` (`7366482`). These are synthetic Workspace
experiments, separate from the three-suite live-controller checks above. LinUCB (a conservative
lower confidence bound here), Thompson sampling and epsilon-greedy support guarded comparisons;
free, pooled-user, counting and broad-grant modes are research ablations, never live providers.

Small smoke commands (new output directories; no sweep):

```bash
python -m grids learning synthesize --output results/learning/world-01 --users 3 --null-users 1 --length 4 --eval-size 6 --canary-size 3
# Existing Laya environment, with HF_HOME pointing to the cache and HF_HUB_OFFLINE=1:
python -m grids learning predict --inputs results/learning/world-01/stream.jsonl results/learning/world-01/eval.jsonl results/learning/world-01/canary.jsonl --metadata workspace/artifacts/laya-pairs-release-v1/metadata/laya-pairs-v1.json --output results/learning/predictions-01.jsonl
python -m grids learning learn --world results/learning/world-01 --predictions results/learning/predictions-01.jsonl --output results/learning/comparison-01 --seeds 1 --no-sweep --workers 1
```

`predict` defaults to pinned Cybersec with rotated options, retaining each order's probabilities.
Matching complete outputs are cache hits without model initialization; changed/incomplete outputs
require a new path. `--model-dir` selects a local candidate and records its file hashes.
`learn` writes `runs.csv`, `summary.csv`, `gate.csv`, and `run.json`. It compares only the stream;
the separate eval/canary files are reserved for future checkpoint validation. This CLI neither
trains nor promotes checkpoints. Synthetic labels and model predictions are not reviewed truth.
