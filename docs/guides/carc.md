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
