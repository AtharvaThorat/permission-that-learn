#!/usr/bin/env bash
# Supply account, partition, and site-approved A100 GRES on the sbatch command.
#SBATCH --job-name=grids
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=02:00:00
#SBATCH --signal=B:USR1@120
set -euo pipefail
: "${SLURM_JOB_ID:?Run inside an approved Slurm allocation, never on a login node}"
: "${RUN_PY:?Set runner Python}" "${ACTOR_PY:?Set selected actor Python}"
: "${PROFILE:?Set actor profile}" "${CONFIG:?Set reviewed experiment config}"
: "${HF_HOME:?Set pinned model cache}" "${PERSISTENT_DIR:?Set approved persistent output directory}"
cd "${SLURM_SUBMIT_DIR:?}"
work="${SLURM_TMPDIR:-$PWD/tmp}/grids-${SLURM_JOB_ID}"
destination="$PERSISTENT_DIR/grids-${SLURM_JOB_ID}"
test ! -e "$work" && test ! -e "$destination"
mkdir -p "$work" "$PERSISTENT_DIR"
actor_pid='' runner_pid=''
stop_group() {
  local pid="$1"
  test -n "$pid" || return 0
  kill -INT -- "-$pid" 2>/dev/null || return 0
  for i in {1..20}; do kill -0 -- "-$pid" 2>/dev/null || return 0; sleep 1; done
  kill -TERM -- "-$pid" 2>/dev/null || true
  sleep 2
  kill -KILL -- "-$pid" 2>/dev/null || true
}
cleanup() {
  local status=$?
  trap - EXIT
  stop_group "$runner_pid"
  stop_group "$actor_pid"
  printf '%s\n' "$status" > "$work/exit-status.txt"
  if ! cp -a -- "$work" "$destination"; then
    echo "COPY FAILED: preserve $work and recover it before scratch expires" >&2
    exit 3
  fi
  echo "Artifacts: $destination"
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM USR1
export HF_HUB_CACHE="$HF_HOME/hub" HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 USE_TF=0 LAYA_CPU_AMP=0
export BLACKBOX_ACTOR_API_KEY="$("$RUN_PY" -c 'import secrets; print(secrets.token_hex(24))')"
"$RUN_PY" -m experiment validate --config "$CONFIG" > "$work/plan.json"
"$RUN_PY" -c 'import os,sys; from experiment.spec import load; from gatekeeper.config import resolve_checkpoint; from gatekeeper.laya_adapter import resolve_local_snapshot; s=load(sys.argv[1]); assert "wall_gatekeeper" not in s.modes or resolve_local_snapshot(*resolve_checkpoint(),s.gatekeeper.cache_dir)' "$CONFIG"
"$RUN_PY" -c 'import json,sys; from experiment.spec import load; s=load(sys.argv[1]); p=json.load(open(sys.argv[2])); assert len(s.actors)==1, "Use one actor phase per batch"; a=next(iter(s.actors.values())).settings; assert (a.model_id,a.model_revision,a.served_model_name)==(p["model_id"],p["revision"],p["served_model_name"]); assert a.base_url.rstrip("/") in ("http://127.0.0.1:8000/v1","http://localhost:8000/v1"); print(p["served_model_name"])' "$CONFIG" "$PROFILE" > "$work/model-name.txt"
"$RUN_PY" -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",8000)); s.close()'
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv > "$work/hardware.txt"
grep -q A100 "$work/hardware.txt" || { echo 'Allocated GPU is not A100' >&2; exit 2; }
"$RUN_PY" -m pip freeze > "$work/runner-packages.txt"
"$ACTOR_PY" -m pip freeze > "$work/actor-packages.txt"
git rev-parse HEAD > "$work/source-revision.txt"
cp -- "$CONFIG" "$work/experiment.json"
cp -- "$PROFILE" "$work/actor-profile.json"
setsid "$ACTOR_PY" scripts/serve_actor.py --profile "$PROFILE" --cache-dir "$HF_HOME" > "$work/actor.log" 2>&1 &
actor_pid=$!
ready=0
for i in {1..180}; do
  if "$RUN_PY" -c 'import json,os,sys,urllib.request; r=urllib.request.Request("http://127.0.0.1:8000/v1/models",headers={"Authorization":"Bearer "+os.environ["BLACKBOX_ACTOR_API_KEY"]}); d=json.load(urllib.request.urlopen(r,timeout=5)); assert sys.argv[1] in [m["id"] for m in d["data"]]' "$(cat "$work/model-name.txt")" 2>/dev/null; then ready=1; break; fi
  kill -0 "$actor_pid" || exit 2
  sleep 5
done
test "$ready" = 1
"$RUN_PY" scripts/validate_model_tool_call.py --model "$(cat "$work/model-name.txt")" --multi-turn --timeout 180 --output "$work/tool-validation.json" > "$work/tool-validation.log"
setsid "$RUN_PY" -m experiment run --config "$CONFIG" --output "$work/results" --allow-models > "$work/runner.log" 2>&1 &
runner_pid=$!
wait "$runner_pid"
runner_pid=''
for run in "$work"/results/*; do
  "$RUN_PY" -m experiment aggregate --run-dir "$run" > "$work/aggregation.log"
  "$RUN_PY" -m experiment report --run-dir "$run"
  "$RUN_PY" -c 'import json,sys; d=json.load(open(sys.argv[1])); assert not any(m.get(k,0) for m in d["metrics"] for k in ("infrastructure_error","invalid_configuration","interrupted","missing")), "Incomplete/infrastructure-failed episodes; inspect artifacts"' "$run/aggregates/summary.json"
done
