#!/usr/bin/env bash
set -euo pipefail

# Person 1: local actor startup and tool-call validation.
export BLACKBOX_ACTOR_API_KEY="${BLACKBOX_ACTOR_API_KEY:-local-validation-only}"
bash scripts/colab_vllm_start.sh "${MODEL_PATH:?Set MODEL_PATH to an existing local model directory}" \
  8000 Qwen2.5-7B-Instruct

# Run these commands from a second shell after vLLM is ready.
# python scripts/validate_model_tool_call.py \
#   --base-url http://127.0.0.1:8000/v1 \
#   --model Qwen2.5-7B-Instruct \
#   --output handoff/validation_response.json

# Person 2: baseline. Use a fresh shell/process after the server is ready.
# python scripts/reset_workspace.py
# python -m experiment run \
#   --config configs/experiments/frozen/unprotected.json \
#   --output results/experiments --allow-models

# Person 3: protected runs. Reset separately before each command.
# python scripts/reset_workspace.py
# python -m experiment run \
#   --config configs/experiments/frozen/wall_only.json \
#   --output results/experiments --allow-models
# python scripts/reset_workspace.py
# python -m experiment run \
#   --config configs/experiments/frozen/wall_gatekeeper.json \
#   --output results/experiments --allow-models

# Aggregate only after all run directories are captured:
# python -m experiment aggregate --run-dir <run-dir>
# python -m experiment compare \
#   --run-dirs <unprotected-dir> <wall-only-dir> <gatekeeper-dir>
