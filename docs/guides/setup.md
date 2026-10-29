# Machine setup and functional checks

Commands assume Linux, Python 3.12, a source checkout at the reviewed revision,
and execution from its root. On Colab use a terminal/CLI script with an allocated
GPU; on CARC run inference only inside a GPU allocation. Do not submit jobs here.
No GPU or new real-Laya checks were executed for this refactor.

## Install and select assets

```bash
git clone https://github.com/AtharvaThorat/permission-that-learn-.git
cd permission-that-learn-
```

Inside the checkout (select the reviewed branch/commit before installing):

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r environments/cpu.txt
python -m grids --help
python -m grids models list
python -m grids benchmark discover
python -m pytest -q -p no:cacheprovider

export PROFILE=configs/models/ministral3-8b.json
export HF_HOME="$PWD/tmp/model-cache"
python -m grids setup --profile "$PROFILE" --work-dir tmp/machine --dry-run
python -m grids setup --profile "$PROFILE" --work-dir tmp/machine
export RUN_PY="$PWD/tmp/machine/runner/bin/python"
export ACTOR_PY="$PWD/tmp/machine/actor-modern/bin/python"
# Qwen2.5: actor/bin/python; Qwen3.5: actor-qwen35/bin/python.

unset HF_HUB_OFFLINE TRANSFORMERS_OFFLINE
"$RUN_PY" -m grids models download --cache-dir "$HF_HOME" --profile "$PROFILE" --laya
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 USE_TF=0 LAYA_CPU_AMP=0
export GRIDS_ACTOR_API_KEY="$(python -c 'import secrets; print(secrets.token_hex(24))')"
```

For persistent machines replace `HF_HOME` and `--work-dir` with approved storage
locations. Optional `models download --all` downloads all seven profiles plus Laya;
it is expensive and Llama requires previously granted access. Setup keeps the Laya
runner separate from actor packages; do not install both stacks into one environment.

## Real Laya and actor checks (explicit inference)

```bash
"$RUN_PY" -m grids validate laya --cache-dir "$HF_HOME" \
  --output results/validation/laya-01 --max-input-tokens 8192 --allow-models
"$ACTOR_PY" -m grids serve --profile "$PROFILE" --cache-dir "$HF_HOME"
```

Keep the server terminal open. In a second terminal with the same environment:

```bash
export MODEL="$(python -c 'import json,os; print(json.load(open(os.environ["PROFILE"]))["served_model_name"])')"
curl --fail --silent -H "Authorization: Bearer $GRIDS_ACTOR_API_KEY" http://127.0.0.1:8000/v1/models
"$RUN_PY" -m grids validate actor --model "$MODEL" --multi-turn \
  --timeout 180 --output results/validation/actor-01.json
```

Check the identity returned by `/models`, then inspect `laya.json` and actor proof.
Laya short/medium probes must have real predictions; inspect token counts, truncation,
initialization and inference errors for long/overflow probes. A successful process
exit or Wall denial alone is not evidence that Laya made the right decision.
Actor validation supplies a controlled simulated tool result; it is not a native task.

## One native task, then one attack

```bash
"$RUN_PY" -m grids benchmark config --base configs/experiments/smoke.json \
  --profile "$PROFILE" --cache-dir "$HF_HOME" --suite workspace \
  --task user_task_10 --clean-only --output tmp/workspace-smoke.json
"$RUN_PY" -m grids benchmark plan --config tmp/workspace-smoke.json
"$RUN_PY" -m grids benchmark run --config tmp/workspace-smoke.json \
  --output results/smoke --allow-models
```

The base selects three modes and one seed (three episodes). Use discovery to choose
a task/objective in Slack or Banking; generate a separate config per suite. For a
single native attack, replace `--clean-only` with `--attacked-only --native-attack
direct --objective injection_task_0` and select a compatible task from discovery.
Native incompatibility is an error; never patch task semantics to make it run.

```bash
"$RUN_PY" -m grids report --run-dir results/smoke/<printed-run-id>
```

Open that run's `report.html`; inspect attempts and JSON/JSONL when pending/error
or scores are missing. A wrong actor answer is not necessarily a pipeline failure.
Stop the actor with Ctrl-C and verify the serving process has exited. Export the
entire run directory (including SQLite/manifests/traces), not only a summary CSV.

For Colab CLI automation, first run `colab --help`, `colab sessions`, and `colab usage`.
Use the installed interface to execute the same commands on the chosen session,
download outputs, stop sessions you started, and verify their final status. No Colab
session has been created or stopped by this refactor. See [CARC](carc.md) for Slurm.
