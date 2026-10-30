#!/usr/bin/env bash
# Python adapter for the existing actor CLI and Slurm workflow.
set -euo pipefail
: "${ACTOR_IMAGE:?Set the pinned Apptainer SIF path}" "${ACTOR_ENV:?Set the container-created venv}"
: "${HF_HOME:?Set the model cache}"
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
test -f "$ACTOR_IMAGE" && test -f "$ACTOR_ENV/pyvenv.cfg"
args=(exec --cleanenv --bind "$repo,$ACTOR_ENV,$HF_HOME" --pwd "$repo")
if [[ "${ACTOR_USE_GPU:-1}" == 1 ]]; then args+=(--nv); fi
if [[ -n "${ACTOR_WORK_DIR:-}" ]]; then args+=(--bind "$ACTOR_WORK_DIR"); fi
for name in HF_HOME HF_HUB_CACHE HF_HUB_OFFLINE TRANSFORMERS_OFFLINE CUDA_VISIBLE_DEVICES GRIDS_ACTOR_API_KEY; do
  if [[ -v "$name" ]]; then export "APPTAINERENV_$name=${!name}"; fi
done
export APPTAINERENV_PYTHONNOUSERSITE=1
exec apptainer "${args[@]}" "$ACTOR_IMAGE" "$ACTOR_ENV/bin/python" "$@"
