# Local/Colab Smoke-Test Handoff

This handoff is for the first local or Google Colab smoke test using
`Qwen/Qwen2.5-7B-Instruct` and `workspace/user_task_0`. It does not use paid
external endpoints. The model must already be available in the local model
directory; the startup script disables downloads.

## Person 1: Start and validate the local actor

1. Start a local vLLM server with an existing model directory:

   ```bash
   export BLACKBOX_ACTOR_API_KEY=local-validation-only
   bash scripts/colab_vllm_start.sh /absolute/path/Qwen2.5-7B-Instruct 8000 Qwen2.5-7B-Instruct
   ```

   In Colab, use the same command after mounting the approved local/model
   storage and installing the already-approved vLLM environment. Do not use a
   hosted or paid endpoint.

2. In a second terminal, validate tool calling:

   ```bash
   export BLACKBOX_ACTOR_API_KEY=local-validation-only
   python scripts/validate_model_tool_call.py \
     --base-url http://127.0.0.1:8000/v1 \
     --model Qwen2.5-7B-Instruct \
     --output handoff/validation_response.json
   ```

   The command must report `validation: passed` and contain a sanitized
   `get_day_calendar_events` call with JSON arguments for `2024-05-15`.
   It does not execute the calendar tool.

3. Preserve the vLLM logs, model path, server version, Python/CUDA/GPU
   versions, and the generated `handoff/validation_response.json`.

## Person 2: Run the unprotected baseline

Use a separately reset environment before the run:

```bash
python scripts/reset_workspace.py
python -m experiment run \
  --config configs/experiments/frozen/unprotected.json \
  --output results/experiments \
  --allow-models
```

Record the printed `run_dir`. Do not modify the frozen configuration or reuse
the environment for a protected run. Preserve actor requests/responses, tool
calls, task outcome, timing, token usage, errors, and generated JSON/CSV files.

On a Colab T4, `person2_unprotected_baseline.ipynb` runs Qwen2.5-7B with the
frozen actor settings on `configs/experiments/panel-15/unprotected.json`: the
five `workspace_pilot.json` cases plus ten in
`configs/blackbox/attacks/workspace_baseline_extension.json`, each clean and
attacked (30 episodes; every injection vector is read by its task's reference
solution). `configs/experiments/pilot-panel/unprotected.json` keeps the five
pilot cases alone (10 episodes). In both, the clean `user_task_0` episode has
the same identity as the frozen single-task baseline. Qwen is loaded 4-bit (bitsandbytes) on a T4 and BF16 on 30 GB+ GPUs;
the precision is recorded. `scripts/person2_validate_run.py` checks the
configuration before the run (`preflight`) and every result after it
(`check-run`); the notebook stops on failed checks. The report
(`scripts/person2_baseline_report.py`) writes an Excel workbook, CSVs and charts
without modifying the run folders.

## Person 3: Run protected modes

Reset the environment separately before each mode:

```bash
python scripts/reset_workspace.py
python -m experiment run \
  --config configs/experiments/frozen/wall_only.json \
  --output results/experiments \
  --allow-models

python scripts/reset_workspace.py
python -m experiment run \
  --config configs/experiments/frozen/wall_gatekeeper.json \
  --output results/experiments \
  --allow-models
```

For the 15-case panel, run `configs/experiments/panel-15/wall_only.json` and
`configs/experiments/panel-15/wall_gatekeeper.json` the same way. They differ from
`panel-15/unprotected.json` only in `name` and `modes`. Pair IDs include absolute
policy paths, so check out the repository at `/content/permission-that-learn` (as
the baseline did) and serve Qwen the same way as the baseline (4-bit on a T4).
Compare with `scripts/person3_analyze_runs.py`; see section 8 of the
[Person 3 report](docs/reports/PERSON3_PROTECTED_SMOKE_REPORT.md).

The gatekeeper configuration additionally requires a local Laya runtime and
existing checkpoint/encoder cache. Do not add `--allow-models` to bypass
missing prerequisites; fix or document the environment instead.

For each protected run, confirm that wall evidence and, for
`wall_gatekeeper`, Laya request/decision evidence are recorded. Confirm that
blocked actions do not execute, approval-required actions remain pending, and
the protected path never silently becomes `unprotected`.

## Comparison and handoff

Compare only runs with matching model, task, seed, AgentDojo revision, and
fresh initial environment. Keep the three run directories unchanged and run:

```bash
python -m experiment aggregate --run-dir <run-dir>
python -m experiment compare --run-dirs <unprotected-dir> <wall-only-dir> <gatekeeper-dir>
```

Do not expand to multiple models, parallel jobs, Jev, approval memory, or a
large benchmark until all three single-task runs produce inspectable artifacts.

## Current validation state

At handoff creation time, no local vLLM server was available and no real model
request was executed. The committed-looking proof file is therefore an honest
sanitized `not_run` record, not a successful benchmark result. Run the
validator after starting the local server to replace it with actual proof.
