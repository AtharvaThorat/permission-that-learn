# CARC / Slurm execution

The portable batch entry is `scripts/carc_a100.sbatch`. Cluster account, partition,
A100 GRES syntax, filesystem and modules must be supplied by the CARC operator.
They are not known/validated here. Do not run inference on a login node or submit
GPU jobs without the user's authorization.

Install the separate runner/actor environments and download pinned assets using
[setup](setup.md) in an approved preparation environment. Use persistent paths for
environments/cache and generate one model/suite experiment config. CPU planning
may run before allocation; install/server compatibility still requires GPU validation.

```bash
export PROFILE=configs/models/ministral3-8b.json
export CONFIG=tmp/workspace-smoke.json
export RUN_PY="$PWD/tmp/machine/runner/bin/python"
export ACTOR_PY="$PWD/tmp/machine/actor-modern/bin/python"
export HF_HOME="$PWD/tmp/model-cache"
export PERSISTENT_DIR=/path/approved/by/your/cluster
"$RUN_PY" -m grids benchmark plan --config "$CONFIG"
bash -n scripts/carc_a100.sbatch
# Only after approval; replace all scheduler placeholders with site-provided values:
sbatch --account=<account> --partition=<partition> --gres=<A100-GRES> \
  --export=ALL scripts/carc_a100.sbatch
```

The script requires a Slurm allocation, validates the spec and pinned local Laya
assets, checks actor/profile identity and a free local port, records hardware/package
provenance, starts the actor, checks readiness and tool use, runs the experiment,
aggregates/reports, then stops both process groups. It copies the entire scratch
directory into a unique `grids-<job-id>` under persistent storage, including failures.
An infrastructure/incomplete outcome fails the batch; pending approval is explicit.

Inspect `exit-status.txt`, `runner.log`, `actor.log`, `tool-validation.json`, and
`results/<run-id>/report.html`. Confirm job completion with the site's `squeue` /
`sacct` commands. If copying fails, recover the printed scratch path before it expires.
A forced node loss/SIGKILL cannot run the cleanup trap; site checkpoint/persistence
procedures still apply. Colab success does not establish CARC compatibility.

After reviewed smoke results, use the same workflow with expanded configs, one
model phase and suite per job. Preserve source config, package versions and all
attempts. Capture action datasets and run the primary evaluation separately using
[experiments](experiments.md); a full native benchmark alone is not authorization accuracy.

## Qwen3.5 installation failure (job 13499742)

The supplied log used the retired `scripts/machine_setup.py`; use the current
reviewed checkout and `python -m grids setup`. The failure happened before inference.
The [vLLM 0.19.1 release](https://pypi.org/project/vllm/0.19.1/#files) publishes
Linux wheels tagged `manylinux_2_31`, requiring glibc 2.31 or newer. Rocky 8 normally
has 2.28: confirm on the actual node. CUDA 12.6.3 being installed does not establish
wheel or driver compatibility. Loading that module addresses `CUDA_HOME` for a
source build, but does not fix an incompatible glibc. Automatic source builds are
now prohibited for actor dependencies.

Before installation, capture:

```bash
uname -m
ldd --version | head -n 1
python3.12 --version
python3.12 -m pip --version
# Inside the allocated GPU node:
nvidia-smi
```

On a compatible Linux host, use normal setup. It resolves binary dependencies
before installation and stops on failure. On older hosts use a site-approved
Apptainer container, or request a newer node; do not upgrade the host glibc.
The container route below is implemented but has NOT been executed on CARC.
Host-driver compatibility and the site's Apptainer policy remain prerequisites.

### Container actor on an older host

Use absolute paths in approved persistent storage for these variables. Keep the
working native runner/Laya environment; only the actor uses the container.
Run preparation on a site-approved preparation node, not during the benchmark.
The digest below pins the official v0.19.1 Linux amd64 image (not ARM).

```bash
export PROFILE=configs/models/qwen35-9b-a100.json
export ACTOR_IMAGE=/approved/storage/vllm-0.19.1.sif
export ACTOR_ENV=/approved/storage/actor-qwen35-container
export HF_HOME=/approved/storage/model-cache
export ACTOR_PY="$PWD/scripts/actor_container_python.sh"
# RUN_PY must point to the existing working runner Python.
command -v apptainer
mkdir -p "$(dirname "$ACTOR_IMAGE")" "$(dirname "$ACTOR_ENV")" "$HF_HOME"
apptainer pull "$ACTOR_IMAGE" docker://vllm/vllm-openai@sha256:89c1d0629d377daa3f7f369cbea6167a7b48ea89aaacd12555e2b0b2f7f740d3
# Use a fresh ACTOR_ENV, preserving the failed native environment for diagnosis.
test ! -e "$ACTOR_ENV"
apptainer exec --cleanenv --bind "$(dirname "$ACTOR_ENV")" "$ACTOR_IMAGE" \
  python3 -m venv --system-site-packages "$ACTOR_ENV"
export ACTOR_USE_GPU=0
chmod +x scripts/actor_container_python.sh
"$ACTOR_PY" -m pip install --dry-run --only-binary=:all: -e . 'vllm==0.19.1' 'transformers==5.6.2'
"$ACTOR_PY" -m pip install --only-binary=:all: -e . 'vllm==0.19.1' 'transformers==5.6.2'
"$ACTOR_PY" -m pip check
"$RUN_PY" -m grids models download --cache-dir "$HF_HOME" --profile "$PROFILE" --laya
```

Stop if any preparation command fails. The external venv inherits the image's
precompiled torch/vLLM stack; do not reuse a native-host venv inside the container.
The adapter binds the repository, model cache, environment and job output path,
forwards the Slurm CUDA device selection and API key without printing it, and uses
Apptainer `--cleanenv --nv`. Container userland does not replace the host driver;
see [Apptainer GPU requirements](https://apptainer.org/docs/user/latest/gpu.html).

Inside an approved GPU allocation, before running any benchmark:

```bash
export ACTOR_USE_GPU=1
"$ACTOR_PY" -m grids validate actor-env --profile "$PROFILE" --gpu \
  --output "tmp/actor-preflight-${SLURM_JOB_ID}.json"
```

This checks pinned package versions, native extension/parser imports, CUDA
availability, precision and a small GPU operation. It does not prove model
loading or tool calling. The batch script additionally requires server readiness
and multi-turn tool-call validation before starting episodes. Start with one task
using the [setup smoke commands](setup.md), then review all three protection modes.
Use the submission commands above with this `ACTOR_PY` and matching `PROFILE` and
`CONFIG` only after approval. `CUDA_MODULE=cuda/12.6.3` is optional for a native
setup; it is not a replacement for compatible wheels or a driver check.

Inspect `actor-preflight.json`, `actor-preflight.log`, `actor-dependencies.txt`,
`actor.log` and `tool-validation.json` in the persisted job directory. A failed
preflight stops the job and preserves diagnostics. Do not launch a full benchmark
until installation, real server/tool checks and the small smoke run pass on CARC.
