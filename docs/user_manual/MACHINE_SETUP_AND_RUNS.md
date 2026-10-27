# Linux / CARC setup and experiment commands

Run from the repository root. This manual prepares a machine and reuses the
existing experiment runner; it does not submit jobs automatically. The CARC
institution, scheduler, account, partition, GPU type and storage policy are not
yet known. Confirm those with your allocation administrator before submission.
Run inference inside an allocated compute job, not on a login node. Prepare
packages/model caches on a node where your site's network policy permits it.

## 1. Clone and install

The setup changes are on `feat/machine-setup-cli`, which includes the earlier
Laya functional fixes. Use that branch until its PR is merged; verify the checkout
contains commits `f5c038a` and `8365f44` before running the commands.

```bash
git clone --branch feat/machine-setup-cli https://github.com/AtharvaThorat/permission-that-learn-.git permission-that-learn
cd permission-that-learn
git rev-parse HEAD
python3.12 --version
python3.12 scripts/machine_setup.py install --work-dir tmp/machine --dry-run
python3.12 scripts/machine_setup.py install --work-dir tmp/machine --component all
```

Use your site's Python 3.12 module if that executable is unavailable. `install`
creates separate `runner/` and `actor/` virtual environments, installs the tested
pins and runs `pip check`. It does not download models, run inference, install
CUDA drivers, or use sudo. Select `--component runner` or `--component actor` to
install only one environment; `--profile configs/actors/<profile>.json` selects
the actor package pins. Existing environments are reused, not deleted. Inspect
an incompatible environment before changing it; prefer a new work directory.
For persistent/scratch storage, replace `tmp/machine` consistently with your
site-approved location. Do not put active SQLite run indexes on shared/network
storage: execute in node-local job storage, then copy the closed run directory
to persistent storage before the job ends.

```bash
RUN_PY=tmp/machine/runner/bin/python
ACTOR_PY=tmp/machine/actor/bin/python
export HF_HOME="$PWD/tmp/machine/hf"
export HF_HUB_CACHE="$HF_HOME/hub"
```

The tested split is vLLM 0.11.0 / Transformers 4.57.6 for serving, and Laya
0.3.28 / Torch 2.14.1 / Transformers 5.20.2 for the runner. See the
[functional handoff](../../SETUP_HANDOFF.md#functional-validation-2026-10-25)
for exact provenance and T4 evidence. Installation on CARC is not yet verified.

## 2. Download only the models you need

```bash
# Baseline actor plus pinned Laya (no inference).
"$RUN_PY" scripts/machine_setup.py download --cache-dir "$HF_HOME" \
  --profile configs/actors/qwen25-7b-t4.json --laya
# Optional alternative only.
"$RUN_PY" scripts/machine_setup.py download --cache-dir "$HF_HOME" \
  --profile configs/actors/qwen3-4b-instruct-t4.json
# Alternatively: all repository actor profiles plus baseline Laya.
"$RUN_PY" scripts/machine_setup.py download --cache-dir "$HF_HOME" --all
```

All revisions come from the profiles/manifest; no floating `main` model download.
These commands cache weights, tokenizer and encoder assets, and print resolved
snapshot provenance. They do not prove loading works. Test Laya inside the job:

```bash
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 USE_TF=0 LAYA_CPU_AMP=0
"$RUN_PY" scripts/validate_laya.py --cache-dir "$HF_HOME" \
  --output results/carc-laya-first-probe --allow-models
```

Choose a new probe output directory for every attempt. Missing assets must be
prepared explicitly; protected execution never falls back to an unprotected run.

## 3. Generate and inspect a configuration

```bash
"$RUN_PY" scripts/machine_setup.py config \
  --base configs/experiments/frozen/unprotected.json \
  --profile configs/actors/qwen25-7b-t4.json --cache-dir "$HF_HOME" \
  --task user_task_10 --clean-only \
  --mode unprotected --mode wall_only --mode wall_gatekeeper \
  --gate-max-input-tokens 8192 --gate-timeout 180 \
  --name carc-smoke --output tmp/carc-smoke.json
"$RUN_PY" -m experiment plan --config tmp/carc-smoke.json
```

Generation validates native task IDs and writes a new file exclusively; it never
overwrites the base or an existing output. Sampling, policy, metadata, seeds,
attacks and budgets are inherited from `--base` except for explicit options.
`--task` replaces **clean** task selection; attacks remain unless `--clean-only`
is specified. Only the existing AgentDojo workspace suite is supported; arbitrary
datasets require a separate integration. Use another base JSON for a different
declared task/attack panel. All commands have `--help`.

The explicit 8192 Laya context/180-second inference timeout are development
settings tested on small CPU checks. They are not an agreed benchmark freeze.
Omitting them preserves the base configuration; frozen 512-token defaults can
still reject full evidence. Align settings across all compared modes and review
the generated plan before approving a panel run.

## 4. Serve and run one actor

Inside the allocated GPU job, with the variables from section 1:

```bash
export BLACKBOX_ACTOR_API_KEY="$("$RUN_PY" -c 'import secrets; print(secrets.token_urlsafe(32))')"
setsid "$ACTOR_PY" scripts/serve_actor.py \
  --profile configs/actors/qwen25-7b-t4.json --cache-dir "$HF_HOME" \
  > tmp/actor.log 2>&1 &
ACTOR_PID=$!
# Stop this process group on shell exit; never use broad pkill commands.
trap 'kill -- -"$ACTOR_PID" 2>/dev/null || true' EXIT
```

Wait for startup in `tmp/actor.log`, then:

```bash
"$RUN_PY" scripts/validate_model_tool_call.py --model Qwen2.5-7B-Instruct \
  --timeout 180 --output results/carc-actor-proof.json
"$RUN_PY" -m experiment run --config tmp/carc-smoke.json \
  --output results/carc --allow-models
```

The server uses only loopback, the profile's pinned cache/template/parser, and
the job's GPU visibility. Do not set `VLLM_USE_V1=0`. Keep the key in environment
variables, not shell tracing, config JSON, notebooks or saved logs. Stop the
server group and check `nvidia-smi` before replacing its model.

## 5. Sequential or parallel models

Repeat `--profile` when generating a configuration. Default sequential mode uses
one port/resource group; **the scheduler does not load or swap model servers**.
Run the first selected actor, stop its server, start the second, then resume:

```bash
"$RUN_PY" scripts/machine_setup.py config --base tmp/carc-smoke.json \
  --profile configs/actors/qwen25-7b-t4.json \
  --profile configs/actors/qwen3-4b-instruct-t4.json \
  --cache-dir "$HF_HOME" --output tmp/carc-two-models.json
"$RUN_PY" -m experiment run --config tmp/carc-two-models.json \
  --actors qwen25-7b-t4 --output results/carc --allow-models
# Record the printed run_dir. Replace the server with the Qwen3 profile on port 8000.
"$RUN_PY" -m experiment resume --run-dir <run-dir> \
  --actors qwen3-4b-instruct-t4 --allow-models
```

For parallel models, generate with `--parallel`. This assigns successive ports
(8000, 8001), separate resource groups and one episode per model. Start one
`serve_actor.py` process for each profile using `--port 8000` / `--port 8001` and
distinct GPUs from your scheduler allocation via each process's
`CUDA_VISIBLE_DEVICES`. Do not assume physical GPU numbers or run both T4 profiles
on one GPU. Start both servers before an unfiltered `experiment run`. Scheduler
resource groups limit concurrency; they do not allocate hardware. Parallel
configuration is CPU-tested, not verified by a real CARC multi-GPU run.

For a panel run, use `--base configs/experiments/panel-15/unprotected.json`, omit
`--task`/`--clean-only`, and explicitly select the intended modes/profiles. Review
job count, budgets, identities and approved gatekeeper settings before execution.
Do not compare these new configurations directly with historical runs unless
the saved identities/settings match. No panel has been executed by this setup work.

## 6. Batch-job template (only if CARC uses Slurm)

For the October 27 three-suite workflow, use
[`scripts/carc_a100.sbatch`](../../scripts/carc_a100.sbatch). It validates the
configuration and assets, checks actor readiness/identity, runs the existing
experiment CLI, produces reports, terminates process groups and copies complete
or interrupted artifacts to the required `PERSISTENT_DIR`. It refuses login-node
execution. It has not been submitted to CARC.

Set `RUN_PY`, `ACTOR_PY`, `PROFILE`, `CONFIG`, `HF_HOME` and `PERSISTENT_DIR` to
approved paths in your allocation. Choose `actor-qwen35/bin/python` with
`configs/actors/qwen35-9b-a100.json`, or retain `actor/bin/python` and the Qwen2.5
profile. Then, **only after owner approval**, submit:

```bash
sbatch --account=<approved-account> --partition=<approved-partition> --gres=<site-A100-resource>:1 scripts/carc_a100.sbatch
```

Confirm the actual GPU resource syntax with USC CARC; do not copy another
institution's `gpu_a100` partition name. See official
[running-jobs guidance](https://www.carc.usc.edu/user-guides/hpc-systems/using-our-hpc-systems/running-jobs)
and [resource overview](https://www.carc.usc.edu/user-guides/hpc-systems/discovery/resource-overview-discovery).
The owner must supply account, cluster/partition, A100 availability and persistent
storage. Colab validation does not establish CARC compatibility.

Save under `tmp/carc-smoke.sbatch`; replace site-specific directives first. This
example assumes packages/assets and `tmp/carc-smoke.json` are already prepared,
and the checkout/results are on job-local storage. Adapt persistence/copy-out to
your site's job-local scratch policy. It is not a tested CARC submission script.

```bash
#!/usr/bin/env bash
#SBATCH --job-name=grids-smoke
#SBATCH --account=REPLACE_WITH_ACCOUNT
#SBATCH --partition=REPLACE_WITH_GPU_PARTITION
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=01:00:00
#SBATCH --output=tmp/grids-%j.log
set -euo pipefail
cd "$SLURM_SUBMIT_DIR"
RUN_PY=tmp/machine/runner/bin/python
ACTOR_PY=tmp/machine/actor/bin/python
export HF_HOME="$PWD/tmp/machine/hf" HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export HF_HUB_CACHE="$HF_HOME/hub" USE_TF=0 LAYA_CPU_AMP=0
export BLACKBOX_ACTOR_API_KEY="$("$RUN_PY" -c 'import secrets; print(secrets.token_urlsafe(32))')"
setsid "$ACTOR_PY" scripts/serve_actor.py --profile configs/actors/qwen25-7b-t4.json \
  --cache-dir "$HF_HOME" > "tmp/actor-${SLURM_JOB_ID}.log" 2>&1 &
ACTOR_PID=$!
trap 'kill -- -"$ACTOR_PID" 2>/dev/null || true' EXIT
ready=0
for attempt in {1..120}; do
  if "$RUN_PY" -c 'import os,urllib.request; urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8000/v1/models",headers={"Authorization":"Bearer "+os.environ["BLACKBOX_ACTOR_API_KEY"]}),timeout=5).close()' 2>/dev/null; then
    ready=1; break
  fi
  kill -0 "$ACTOR_PID" || exit 1
  sleep 5
done
test "$ready" = 1
"$RUN_PY" -m experiment run --config tmp/carc-smoke.json --output results/carc --allow-models
```

After adapting it: `sbatch tmp/carc-smoke.sbatch`, `squeue -u "$USER"`, and
`scancel <job-id>` to cancel your job. Confirm termination through the scheduler.
If CARC uses another scheduler, obtain its equivalent allocation/submission
commands; the Python setup/run commands remain the same.

## 7. Results, resume and handoff

```bash
"$RUN_PY" -m experiment aggregate --run-dir <run-dir>
"$RUN_PY" -m experiment report --run-dir <run-dir>
# Only when intentionally retrying failed attempts, with unchanged source/spec:
"$RUN_PY" -m experiment resume --run-dir <run-dir> \
  --retry-status infrastructure_error --allow-models
```

Open the printed HTML file after copying the whole closed run directory locally.
Keep every attempt and its raw JSON/JSONL. Default aggregation chooses the earliest
attempt, not the best score. Resume reruns interrupted episodes; it does not restore
in-memory tool state or approve saved ASK requests. Source/config changes require
a new run. A process killed by the scheduler may leave an incomplete attempt;
keep it and use the existing resume/aggregation tools rather than deleting it.

Before declaring CARC readiness: record GPU/driver, package versions, model
revisions, generated configuration, plan, real tool probe, Laya diagnostics,
native scores and reports. Verify ALLOW dispatch, pending ASK without dispatch,
and fail-closed errors. Update the [tracker](../project_tracking.md) and
[Week 2 task](../process_documentation/week2-24-10-2026/week_2_tasks.md).
