# Curated research results

[Current research release](research-release/README.md) provides selected aggregate evidence,
a portable HTML report and source hashes. Results are labeled as constructed security checks,
real inference smoke checks, or provisional-label comparisons. Raw local runs remain ignored.

Historical studies below retain their original interpretation and provenance. They must not
be pooled with current results as if they used the same labels, policy or implementation.

`laya-permission-v1/` is a curated training dataset with its own card, label guide,
review sheet and file hashes. It is not an evaluation result and its labels are not
independent authorization ground truth. `laya-permission-v1-compact/` holds the same rows
with `context` reduced by `compact_v1` for 1,024-token Laya checkpoints.

`memory-sim/` is an offline simulation of approval memory with simulated users on the same 450 actions. Its users
and metrics use the LLM-reviewed labels; it is not a real-model or human-user result.

`permission-memory/` compares counting memory with scoped grants on Siddharth Magesh's gated laya-pairs-v1 release
(not redistributed; hashed). It holds LLM-reviewed labels, real Laya-Cybersec CPU predictions (single order and the rotated-options method) and a
simulated-user run; it is not a human-labelled or live result.
