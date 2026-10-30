# CARC actor installation reliability

Branch: `fix/carc-actor-wheel-preflight`. No push, main merge or GPU submission.

## Cause and changes

User-supplied job 13499742 logs show vLLM 0.19.1 falling back to its source archive
and failing for missing CUDA_HOME before inference. Published Linux wheels require
glibc >=2.31; the reported Rocky 8 module path suggests an older host, but actual
`ldd`, Python, architecture and driver outputs remain necessary. CUDA toolkit
availability alone is not a wheel/runtime compatibility check.

Actor setup now checks host compatibility and resolves binary dependencies before
installation, with no automatic source fallback. `validate actor-env` checks pinned
packages, imports, parser registration and optionally a small CUDA operation;
failed reports include host details and cannot overwrite prior reports. Slurm
runs it before serving and retains failure logs through the existing cleanup.
An optional pinned Apptainer Python adapter reuses the same serving/batch path,
forwards GPU visibility and binds outputs without changing runner/Laya packages.
See [CARC commands](../guides/carc.md) for native/container preparation and smoke checks.

## Executed verification

Using the existing `tmp/d8-testenv` Python environment:

- `python -m pytest tests/integration/test_machine_setup.py tests/unit/test_actor_preflight.py -q -p no:cacheprovider --tb=short`: **11 passed**.
- Initial full run: 264 passed, two subprocess import failures because this legacy
  environment lacked the current editable `grids` package. Installed `-e . --no-deps`;
  reran `python -m pytest -q -p no:cacheprovider --tb=short`: **266 passed**.
- `python -m ruff check src tests`: passed (Ruff 0.14.3).
- `bash -n scripts/carc_a100.sbatch` and `bash -n scripts/actor_container_python.sh`: passed.
- `git diff --check`: passed.
- Pip binary-only cross-platform resolution with Python 3.12/abi3 rejected
  `manylinux_2_28_x86_64` for vLLM 0.19.1 and selected the published wheel with
  `manylinux_2_31_x86_64`. Stopped the latter download; no vLLM installed.

## Remaining validation

The Apptainer image and real CUDA/model execution were not tested locally. Confirm
site Apptainer availability, actual host driver/library compatibility and image
Python version; run dependency checks, GPU preflight, server/tool validation and
one-task smoke before expanding benchmarks. No claims of universal failure-free
execution, real-model success or CARC compatibility follow from CPU tests.
The original retired setup-script path indicates the failed job used older code;
select the reviewed repair commit before preparing the next job.
