# Curated research results

Future reviewed result summaries belong in `docs/results/<meaningful-experiment>/`.
Each summary must identify the question, source revision, configuration/dataset/label
hashes, models, hardware, command, artifact location, metrics and limitations.
Separate controlled tests, real inference and reviewed-label authorization accuracy.

Raw generated artifacts belong in ignored root `results/` and approved persistent
storage. Preserve unique attempts and manifests. Do not commit credentials, caches,
model weights, or unchecked raw traces. There are no new research results from this
refactor; historical tracked reports are available in Git.

`laya-permission-v1/` is a curated training dataset with its own card, label guide,
review sheet and file hashes. It is not an evaluation result and its labels are not
independent authorization ground truth. `laya-permission-v1-compact/` holds the same rows
with `context` reduced by `compact_v1` for 1,024-token Laya checkpoints.
