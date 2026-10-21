# Colab trial

For the corrected Python/dependency setup and a timed five-task pilot, follow
[COLAB_BENCHMARK.md](COLAB_BENCHMARK.md). It incorporates the executed notebook's
findings and produces a presentation report and ZIP.

`scripts/colab_blackbox.py` automates setup for one interactive Colab/Linux GPU
session. This is a proposed deployment profile, not a successful Colab run report.
The existing Windows CPU suite was reported by the user as 68 passed in 11.23s.
The supplied Colab notebook subsequently recorded 75 CPU tests passing, asset
preparation, and actor startup after a Transformers pin correction. Its task
ended in infrastructure_error before any tool dispatch; successful end-to-end
task execution remains unverified. No GPU work was performed locally.

## Before cloning

The new implementation and cleanup are currently local, uncommitted changes.
Commit and push the reviewed files on `feature/agentdojo-blackbox` first; a clone
cannot see local changes. Use a Git clone: a ZIP has no source commit for the
manifest. Do not initialize a synthetic repository to mask that missing provenance.

For a private repository, authenticate using your normal GitHub/Colab secret
workflow. Do not put an access token in a shared notebook or clone URL.

## Notebook cells

Select **Runtime → Change runtime type → GPU**. Use Linux Python 3.10–3.12
(3.12 is the intended starting point). The script stops if no suitable GPU exists.
Replace the URL if using a fork and clone only after the branch is pushed:

```python
!git clone --branch feature/agentdojo-blackbox --single-branch https://github.com/AtharvaThorat/permission-that-learn-.git /content/permission-that-learn
%cd /content/permission-that-learn
!pip -q install uv
!uv python install 3.12
!uv venv --seed --python 3.12 /content/py312
```

Run the CPU tests first. This installs the test requirements into an isolated
environment; it needs no GPU or model weights:

```python
!/content/py312/bin/python scripts/colab_blackbox.py tests
```

Prepare the full trial. This installs separate actor and gate environments,
runs the CPU tests, downloads Qwen's original weights, and loads the pinned Laya
checkpoint once on CPU so its encoder/tokenizer dependencies are downloaded too.
It then checks that Laya loads in a fresh offline process:

```python
!/content/py312/bin/python scripts/colab_blackbox.py prepare
```

The original Qwen files are around 16.4 GB even though the server quantizes them
to 4-bit during loading. Allow at least 45 GiB free disk initially for models and
two Python environments. Initial installation/downloads can take considerable
time. Reruns reuse the environments and cached assets. For repeatable model
selection, pass `--actor-revision <40-character-Qwen-commit>` to prepare; otherwise
the first prepare resolves and records the commit and later prepares reuse it.

List real task IDs and prompts:

```python
!/content/py312/bin/python scripts/colab_blackbox.py list-tasks
```

Choose one task (prefer a read-only task for the first trial), replace the
placeholder, and run it:

```python
!/content/py312/bin/python scripts/colab_blackbox.py run --task <TASK_ID> --native-raw-logs
```

The helper writes a config with that one task, runs preflight, starts a local
authenticated actor server, waits for readiness, invokes the existing runner,
and terminates its server process group on completion/error. No external tunnel
or remote service is needed. The key is generated in memory, not saved in config.
The `--native-raw-logs` switch permits AgentDojo's synthetic transcript logging.
Run cells interactively in Colab; free runtimes are not guaranteed persistent
hosting. Save your outputs before Colab resets the runtime.

Outputs default to `/content/blackbox-colab/`:

| Path | Meaning |
|---|---|
| `actor-server.log` | Latest server startup/run diagnostics (overwritten each invocation) |
| `assets.json` | Exact selected model revisions and quantization metadata |
| `gate-freeze.txt`, `actor-freeze.txt` | Resolved packages for the respective environments |
| `experiment.local.json` | Config for the most recent invocation |
| `runs/<run-id>/` | Manifest, events, native transcripts, and scores |

To keep the results, use the Colab Files panel to download them or copy this output
directory to your Drive. Avoid copying `gate/`, `actor/`, or `hf/` unless you
intentionally want to retain the environments/model cache.

## Profile and limits

- Qwen3-8B with bitsandbytes 4-bit inflight quantization, FP16 compute, one request
  at a time, 8192 total context tokens, 1024 maximum output tokens, eager execution.
  This is a different precision profile from the original full-precision recipe.
- Actor dependencies: vLLM 0.11.0, Transformers 4.57.6, and bitsandbytes >=0.46.1,<0.49. The
  selected vLLM wheel requires a compatible NVIDIA driver/CUDA environment. The
  GPU check rejects pre-Turing GPUs and GPUs with less than about 14 GiB VRAM;
  passing the check does not guarantee enough host RAM or successful loading.
- CPU gate: original pinned Laya model and laya==0.3.28. Linux dependencies resolve
  independently of the preserved Windows lock; `pip check` and resolved package
  inventories are recorded. No silently substituted model or gate is used.
- The unchanged reference wall blocks recipients outside its empty allowlists;
  writes can stop for approval. A completed run can report low utility or pending
  approval. Review the policy before interpreting the result.
- Long conversations may exceed the 8K server context. They fail visibly; the
  helper does not silently truncate tools/history. This profile is for small
  trials, not a claim of full-suite coverage or training capability.
- `--mode wall_only`, `wall_rules`, or `unprotected` explicitly selects comparison
  modes. Use identical task/model/policy selections when comparing outcomes.

If install fails, inspect pip's conflict rather than treating prepare as complete.
For startup failure inspect `actor-server.log`; GPU memory, system RAM, Python,
driver, and dependency compatibility can all matter. This helper requires no API
provider credit but uses your allocated notebook resources.

Sources: [Colab availability/limits](https://research.google.com/colaboratory/faq.html),
[vLLM 0.11 GPU requirements](https://docs.vllm.ai/en/v0.11.0/getting_started/installation/gpu.html),
[vLLM bitsandbytes serving](https://docs.vllm.ai/en/v0.11.0/features/quantization/bnb.html),
[Qwen model files](https://huggingface.co/Qwen/Qwen3-8B/tree/main).
