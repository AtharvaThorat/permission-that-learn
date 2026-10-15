# Separate actor-server environment — NOT RUN

The CPU requirements preserve the existing Laya lock. Prepare vLLM in a separate
Linux environment using an explicitly selected Python, CUDA, GPU driver and exact
vLLM version compatible with the user's hardware. Versions, available memory,
quantization and the actor revision remain unresolved. No solved server lock is claimed.

Future user commands, after selecting the variables (not run here):

```bash
python3 -m venv .venv-actor
source .venv-actor/bin/activate
python -m pip install "vllm==${VLLM_VERSION:?set an exact version first}"
bash scripts/serve_blackbox_actor.sh "$ACTOR_LOCAL_MODEL_PATH" Qwen3-8B "$VLLM_VERSION"
```

The launch script requires existing local safetensors weights, model configuration
and tokenizer configuration. It does not download packages or assets. Offline flags
remain set. Missing shards/tokenizer assets can still cause a later load failure.

The recipe uses the local tokenizer's Hermes-capable template. Every client request
sends `chat_template_kwargs: {enable_thinking: false}`. Qwen documents the parser and
request field in its [function calling guide](https://qwen.readthedocs.io/en/latest/framework/function_call.html).
The [model card](https://huggingface.co/Qwen/Qwen3-8B) documents the thinking switch.
Verify flags and `VLLM_API_KEY` with the exact selected server version later; record
the version, template provenance, revision and quantization in the personal config.

The server binds loopback. A remote GPU host requires an explicit user-managed
port tunnel or authenticated endpoint. No CARC account, partition, GPU type or
job submission is assumed.
