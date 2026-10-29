# Acting model profiles

Seven total profiles retain both Qwen configurations and add five alternatives.
Each JSON pins a 40-character checkpoint revision, template source, parser, package
versions, precision, context and server limits. Exact revisions in the JSON files
are authoritative; model cards explain capabilities and license terms.

| Profile in `configs/models/` | Official model | Parser | License / access |
|---|---|---|---|
| `qwen25-7b-t4.json` | [Qwen2.5-7B-Instruct](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct) | hermes | Apache-2.0 |
| `qwen35-9b-a100.json` | [Qwen3.5-9B](https://huggingface.co/Qwen/Qwen3.5-9B) | qwen3_coder | Apache-2.0 |
| `ministral3-8b.json` | [Ministral 3 8B](https://huggingface.co/mistralai/Ministral-3-8B-Instruct-2512-BF16) | mistral | Apache-2.0 |
| `llama31-8b.json` | [Llama 3.1 8B Instruct](https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct) | llama3_json | Llama 3.1 license; gated access |
| `granite4-micro.json` | [Granite 4.0 Micro](https://huggingface.co/ibm-granite/granite-4.0-micro) | granite4 | Apache-2.0 |
| `smollm3-3b.json` | [SmolLM3 3B](https://huggingface.co/HuggingFaceTB/SmolLM3-3B) | hermes | Apache-2.0 |
| `phi4-mini.json` | [Phi-4 Mini Instruct](https://huggingface.co/microsoft/Phi-4-mini-instruct) | phi4_mini_json | MIT |

Selection favors distinct model families with documented tool use, modest model
size and available vLLM parsers. This is a compatibility candidate set, not a quality
ranking. The [vLLM parser documentation](https://docs.vllm.ai/en/v0.19.1/features/tool_calling/)
and pinned parser registry were checked; GPU loading/tool use has **not** been
validated for the five additions. No claim of superiority over Qwen is made.

New profiles target A100 40GB: BF16, 8192 context, one sequence, 85% memory allocation,
eager execution. Weight size alone does not establish fit: runtime, vision components
where present, activations and KV cache need actual measurements. Qwen2.5 retains
its separate vLLM 0.11 / Transformers 4.57 / bitsandbytes environment; Qwen3.5 and
new profiles use vLLM 0.19.1 / Transformers 5.6.2 in separate actor environments.
Ministral uses the Mistral tokenizer/config/load modes. Thinking controls are explicit
where supported. None of these settings change the controller or native scoring.

Use `python -m grids models list` to inspect pins. Follow [setup](setup.md) for
selected downloads and controlled multi-turn validation before collecting data.
Do not download all models by default or commit access tokens.
