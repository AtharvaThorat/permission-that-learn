#!/usr/bin/env bash
# FOR LATER USER EXECUTION on a separately prepared Linux GPU environment.
set -euo pipefail
model_path="${1:?Existing absolute local model directory required}"
served_name="${2:?Served model name required}"
expected_vllm="${3:?Exact installed vLLM version required}"
[[ "$model_path" = /* && -d "$model_path" ]] || { echo 'Expected an existing absolute local model directory' >&2; exit 2; }
[[ -f "$model_path/config.json" && -f "$model_path/tokenizer_config.json" ]] || { echo 'Local model/tokenizer configuration is missing' >&2; exit 2; }
find "$model_path" -maxdepth 1 -name '*.safetensors' -print -quit | grep -q . || { echo 'Local safetensors weights are missing' >&2; exit 2; }
: "${BLACKBOX_ACTOR_API_KEY:?Set the local server credential}"
actual_vllm="$(python -c 'from importlib.metadata import version; print(version("vllm"))')"
[[ "$actual_vllm" = "$expected_vllm" ]] || { echo 'Installed vLLM version differs from selected version' >&2; exit 2; }
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export VLLM_API_KEY="$BLACKBOX_ACTOR_API_KEY"
# The client sends chat_template_kwargs.enable_thinking=false on every request.
# Verify hermes and VLLM_API_KEY support in the selected server version later.
exec vllm serve "$model_path" --tokenizer "$model_path" \
  --served-model-name "$served_name" --host 127.0.0.1 --port 8000 \
  --enable-auto-tool-choice --tool-call-parser hermes
