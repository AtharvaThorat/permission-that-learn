# Project tracking

Updated 2026-11-03. Use the [documentation index](README.md) for commands and
architecture, and the [refactor milestone](milestones/2026-10-refactor.md) and
[training-data](milestones/2026-11-laya-training-data.md) and
[compact_v1](milestones/2026-11-laya-compact.md) milestones for evidence.

## Current objective

Evaluate authorization on identical frozen actions/context using independent
ALLOW/BLOCK/ASK labels. Native AgentDojo utility and attack success remain secondary.
The labeled authorization benchmark is not yet available.

## Implemented and CPU-verified

- One `src/grids` package and CLI: shared controller, Wall, Laya adapter, actors,
  native suites, scheduler, unique attempts and reports.
- Decision-time capture, immutable datasets, three offline comparators, independent
  label import, paired metrics, coverage and HTML/CSV/JSON reports.
- Workspace, Slack and Banking retain native tasks/attacks/scoring and three live
  modes. Exact approval binding, fail-closed errors and recovery tests remain.
- Seven pinned actor profiles: both Qwens plus Ministral, Llama, Granite, SmolLM
  and Phi. Profile/command checks pass; GPU compatibility is separate.
- Consolidated dependencies, docs and notebooks; removed obsolete tracked wrappers,
  panels and reports. Local raw results, environments and caches retained.
- Final CPU regression: **262 passed**; Ruff passed. No real models run in this refactor.
- Laya fine-tuning data (2026-11-02, branch `data/laya-permission-v1`): `grids training-data`
  and [laya-permission-v1](results/laya-permission-v1/README.md), 300 train (Slack, Banking) and
  150 test (Workspace) rows, 100/50 per label, exact Laya input in `context`, deterministic
  builds. Labels reviewed by Claude, not a human. CPU regression **273 passed**.
- compact_v1 Laya input (2026-11-03, branch `data/laya-permission-v1-compact`): `compact()` in
  `gatekeeper/context.py` as input profile `compact_v1`, and
  [laya-permission-v1-compact](results/laya-permission-v1-compact/README.md). All 450 rows fit 1,024 tokens
  with Laya-Cybersec and pinned Laya tokenizers (max 764 context tokens); injected evidence kept in 119/119.
  CPU regression **282 passed**.

## Remaining work

1. User review/PR merge; no agent push or merge into `main`.
2. Define collection/sampling and independent annotation/adjudication, then import
   reviewed labels. Do not report authorization accuracy before labels exist.
3. Validate five new actor candidates on allocated hardware; repeat real Laya and
   small native end-to-end checks after migration before full benchmarks.
4. Investigate semantic authorization quality with reviewed evidence. The earlier
   implementation recorded a Slack malicious-message ALLOW; this refactor does
   not fix that model decision or establish robust protection.
5. Confirm CARC account/partition/GRES/storage and validate the batch workflow
   on-site. Obtain approval before submission. Suspended-action continuation after
   process exit remains unsupported; only live exact-bound approval can dispatch.
6. Evaluate a newer AgentDojo revision/local clone separately. The pin is unchanged;
   full benchmarks and model-quality comparisons were not run here.
7. Serialize Wall identities and policies deterministically: frozensets currently change
   `permission-context.json`, frozen `context_id` and the Laya input across processes
   (see the training-data milestone).
8. Have people relabel at least the training-data test split before reporting accuracy on it,
   then fine-tune Laya and validate it with real inference.
9. Pass tool history and trusted identities into the live Laya input (`gatekeeper_adapter`), which today carries
   neither, so live `compact_v1` states match training; verify `TextCortex/laya-cybersec` before pinning it.

Historical task details remain in Git. Retained local raw artifacts are not proof
of real-model validation of the refactor.
