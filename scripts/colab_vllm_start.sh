#!/usr/bin/env bash
set -euo pipefail

# Start an already-downloaded local vLLM server for the frozen smoke test.
# This script never downloads model weights and binds only to loopback.
model_path="${1:?Usage: $0 /absolute/local/model/path [port] [served-name]}"
port="${2:-8000}"
served_name="${3:-Qwen2.5-7B-Instruct}"

[[ "$model_path" = /* && -d "$model_path" ]] || {
  echo "Expected an existing absolute local model directory: $model_path" >&2
  exit 2
}
[[ -f "$model_path/config.json" && -f "$model_path/tokenizer_config.json" ]] || {
  echo "Model config/tokenizer files are missing" >&2
  exit 2
}
find "$model_path" -maxdepth 1 \( -name '*.safetensors' -o -name '*.bin' \) \
  -print -quit | grep -q . || {
  echo "Local model weights are missing" >&2
  exit 2
}
: "${BLACKBOX_ACTOR_API_KEY:?Set BLACKBOX_ACTOR_API_KEY to a local test value}"

export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export VLLM_API_KEY="$BLACKBOX_ACTOR_API_KEY"

exec vllm serve "$model_path" \
  --tokenizer "$model_path" \
  --served-model-name "$served_name" \
  --host 127.0.0.1 \
  --port "$port" \
  --max-model-len "${VLLM_MAX_MODEL_LEN:-8192}" \
  --max-num-seqs "${VLLM_MAX_NUM_SEQS:-1}" \
  --gpu-memory-utilization "${VLLM_GPU_MEMORY_UTILIZATION:-0.85}" \
  --enable-auto-tool-choice \
  --tool-call-parser hermes
