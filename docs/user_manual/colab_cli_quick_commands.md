# Google Colab CLI — Quick Commands

Run these commands in Windows PowerShell.

## Create GPU sessions

```powershell
# T4 — tested successfully
colab new -s sam-t4 --gpu T4

# A100 — documented; availability depends on your account
colab new -s sam-a100 --gpu A100
```

## Run local Python scripts on Colab

```powershell
# T4
colab exec -s sam-t4 -f .\train.py

# A100
colab exec -s sam-a100 -f .\run_eval.py
```

## Check sessions and compute usage

```powershell
colab sessions
colab status -s sam-t4
colab usage
```

## Install packages / download weights

```powershell
colab install -s sam-t4 torch transformers
colab download -s sam-t4 /content/model_weights.pth .\model_weights.pth
```

## Stop sessions

```powershell
colab stop -s sam-t4
colab stop -s sam-a100
```

## Notes

- `colab exec` successfully ran `train.py` on the T4.
- A100 creation/execution commands are documented, but the full workflow has not yet been verified.
- Native Windows SSH failed. Use Ubuntu/WSL for further SSH testing.
- Session listing and stopping showed a state mismatch. Verify that a session has actually stopped rather than assuming the command succeeded.

## GRIDS pinned validation workflow (October 27)

The generic examples above are historical CLI checks. For GRIDS, use isolated
environments below, not an unpinned `colab install torch transformers`. CLI 0.7.5
was inspected. Qwen3.5 startup/tool calling was verified on A100-SXM4-40GB.
CARC compatibility still requires a site smoke test. See the
[implementation evidence](../process_documentation/week2-24-10-2026/SIDDHARTH_TASK1_COMPLETION.md).

Validation scope: 37 real native attempts, 292 CPU tests passed (one skipped).
The Qwen2.5 Slack attack succeeded even with Wall + Laya; Laya incorrectly
authorized an unsolicited message. Protected Workspace still produced ASK.
These commands reproduce a functional research pipeline, not a proven defense.
Review these outcomes before approving full experiments. Task Colab sessions
were stopped and zero active assignments/usage rate verified.

```powershell
colab version
colab sessions
colab usage
colab new -s grids-a100 --gpu A100
colab status -s grids-a100
colab exec -s grids-a100 -f tmp/grids_commands.py --timeout 3600
```

Put Linux commands in a local scratch Python script, using
`subprocess.run(['bash', '-lc', r'''...commands...'''], check=True)`.
Run from the repository root on the remote machine. Clone the owner-published,
reviewed commit first; unpushed local work is not available through `git clone`.
Alternatively use `colab upload` to transfer a source-only ZIP and extract it;
never include `.env`, credentials, environments, caches or model weights.

```bash
git clone https://github.com/AtharvaThorat/permission-that-learn-.git grids
cd grids
git switch <reviewed-branch-or-commit>
export WORK="$PWD/tmp/machine" HF_HOME="$PWD/tmp/model-cache"
python3.12 scripts/machine_setup.py install --work-dir "$WORK" --component all --profile configs/actors/qwen25-7b-t4.json
python3.12 scripts/machine_setup.py install --work-dir "$WORK" --component actor --profile configs/actors/qwen35-9b-a100.json
export RUN_PY="$WORK/runner/bin/python"
"$RUN_PY" scripts/machine_setup.py download --cache-dir "$HF_HOME" --laya --profile configs/actors/qwen25-7b-t4.json --profile configs/actors/qwen35-9b-a100.json
export HF_HUB_CACHE="$HF_HOME/hub" HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 USE_TF=0 LAYA_CPU_AMP=0
"$RUN_PY" scripts/validate_laya.py --cache-dir "$HF_HOME" --output results/laya-default --allow-models
"$RUN_PY" scripts/validate_laya.py --cache-dir "$HF_HOME" --output results/laya-8192 --max-input-tokens 8192 --input-profile evidence_v2 --allow-models
"$RUN_PY" -m experiment discover --suite workspace --suite slack --suite banking > tmp/native-discovery.json
```

Use Linux Python 3.12 (install via `uv python install 3.12` if unavailable).
Output directories must be new. Laya uses CPU float32; 8192 is the tokenizer and
encoder ceiling, not a validated accuracy guarantee. The shipped checkpoint
defaults to 512; preflight rejects evidence that cannot fit without truncation.

Start **one** actor. Preserve these shell environment variables for the runner;
separate `colab exec` shell processes do not inherit earlier shell exports.

```bash
export BLACKBOX_ACTOR_API_KEY="$("$RUN_PY" -c 'import secrets; print(secrets.token_hex(24))')"
# Qwen2.5 baseline:
PROFILE=configs/actors/qwen25-7b-t4.json
ACTOR_PY="$WORK/actor/bin/python"
MODEL=Qwen2.5-7B-Instruct
# For Qwen3.5 instead, use:
# PROFILE=configs/actors/qwen35-9b-a100.json
# ACTOR_PY="$WORK/actor-qwen35/bin/python"
# MODEL=Qwen3.5-9B
setsid "$ACTOR_PY" scripts/serve_actor.py --profile "$PROFILE" --cache-dir "$HF_HOME" > tmp/actor.log 2>&1 &
ACTOR_PID=$!
trap 'kill -- -"$ACTOR_PID" 2>/dev/null || true' EXIT
# Run after the log reports server readiness; it verifies model identity too:
"$RUN_PY" scripts/validate_model_tool_call.py --model "$MODEL" --multi-turn --timeout 180 --output results/tool-validation.json
```

Qwen3.5 pins vLLM 0.19.1 / Transformers 5.6.2, BF16, 8192 context, one request,
`qwen3_coder`, `qwen3` reasoning parser, and non-thinking chat-template settings.
Qwen2.5 retains vLLM 0.11.0 / Transformers 4.57.6 and bitsandbytes quantization.
The [official model card](https://huggingface.co/Qwen/Qwen3.5-9B) and
[vLLM recipe](https://recipes.vllm.ai/Qwen/Qwen3.5-9B) informed the new profile.
No model-quality superiority is claimed.

Generate clean, attacked-only, or combined experiments without editing source:

```bash
"$RUN_PY" scripts/machine_setup.py config --base configs/experiments/frozen/unprotected.json --profile "$PROFILE" --cache-dir "$HF_HOME" --output tmp/slack-clean.json --name slack-clean --suite slack --task user_task_0 --clean-only --mode unprotected --mode wall_only --mode wall_gatekeeper --gate-input-profile evidence_v2 --gate-max-input-tokens 8192 --gate-timeout 300
"$RUN_PY" -m experiment plan --config tmp/slack-clean.json
"$RUN_PY" -m experiment run --config tmp/slack-clean.json --output results/smokes --allow-models
"$RUN_PY" scripts/machine_setup.py config --base tmp/slack-clean.json --profile "$PROFILE" --cache-dir "$HF_HOME" --output tmp/slack-attack.json --name slack-attack --native-attack direct --objective injection_task_1 --attacked-only
"$RUN_PY" -m experiment run --config tmp/slack-attack.json --output results/smokes --allow-models
```

For the other representative smoke cases, use Workspace `user_task_10` /
`injection_task_0`, and Banking `user_task_1` / `injection_task_0`. Omit
`--clean-only`/`--attacked-only` to include both. Native templates currently
supported offline: `direct`, `ignore_previous`, `system_message`, `injecagent`.
Their generated payloads are frozen and checked against pinned AgentDojo.
Cases with no native injection candidate remain explicit, not silently skipped.

Prepare the three full suites **only after reviewing smoke results and obtaining
compute approval**. This generates plans; it does not launch model servers:

```bash
for SUITE in workspace slack banking; do
  "$RUN_PY" scripts/machine_setup.py config --base configs/experiments/frozen/unprotected.json --profile "$PROFILE" --cache-dir "$HF_HOME" --output "tmp/$SUITE-panel.json" --name "$SUITE-panel" --suite "$SUITE" --all-tasks --native-attack direct --all-objectives --seed 0 --repetitions 1 --mode unprotected --mode wall_only --mode wall_gatekeeper --gate-input-profile evidence_v2 --gate-max-input-tokens 8192 --gate-timeout 300
  "$RUN_PY" -m experiment plan --config "tmp/$SUITE-panel.json"
  # After approval, while the matching actor is serving:
  # "$RUN_PY" -m experiment run --config "tmp/$SUITE-panel.json" --output results/panels --allow-models
done
```

Repeat `--profile` for multiple models; use `--actors <profile-stem>` to run one
server phase, stop that server, start the next profile, then `experiment resume
--run-dir <run> --actors <next-profile-stem> --allow-models`. `--parallel` requires
separate provisioned servers/GPUs; scheduler groups do not allocate hardware.
Distinct seeds and `--repetitions` expand unique jobs. Repetition is the historical
ordinal of the expanded seed sequence. Native tool arguments are not repaired.

```bash
"$RUN_PY" -m experiment aggregate --run-dir <run-directory>
"$RUN_PY" -m experiment report --run-dir <run-directory>
# Optional live operator channel; use another terminal for feedback:
"$RUN_PY" -m experiment run --config tmp/slack-clean.json --output results/operator --allow-models --approval-dir tmp/approvals --approval-wait-seconds 60
"$RUN_PY" -m experiment approval --pending tmp/approvals/<pending-id>.json --decision approve
# Use --decision reject to reject. Expiry is also bounded by the action TTL.
```

Open the printed HTML report with the entire run folder beside it. JSON/JSONL,
SQLite index, every attempt, native scores and CSVs remain authoritative.
Earliest-attempt aggregation is default; missing metrics stay missing. An ASK
without a live operator leaves only its episode pending. Saved approvals cannot
continue a terminated episode; `resume` retries episodes, not suspended actions.
Version-2 results separate prepared payload input from confirmed response-based
exposure; malicious-action classification remains unknown without review.

Export a ZIP containing results/logs (exclude credentials), then:

```powershell
colab download -s grids-a100 /content/grids-results.zip results/grids-results.zip
colab stop -s grids-a100
colab sessions
colab usage
```

If allocation creates an untracked `[?]` assignment, do not allocate repeatedly
or assume shutdown succeeded. Reconcile that endpoint before further compute.
CARC uses [the batch script](../../scripts/carc_a100.sbatch); site account,
partition, A100 resource name and persistent path must be supplied by the owner.
No CARC submission is performed automatically.
