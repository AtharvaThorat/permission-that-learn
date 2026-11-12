# Project tracking

Updated 2026-11-11. Use the [documentation index](../README.md) for commands and
architecture, and the [refactor milestone](../archive/milestones/2026-10-refactor.md) and
[training-data](../archive/milestones/2026-11-laya-training-data.md) and
[compact_v1](../archive/milestones/2026-11-laya-compact.md) and
[approval memory](../archive/milestones/2026-11-approval-memory.md) and
[permission memory](../archive/milestones/2026-11-permission-memory.md) milestones for evidence.

## Local research release preparation

Branch `codex/research-release` builds on `4d8f1fb`; prepared locally, no push or main merge.
- Research README links the supplied manuscript, shared pipeline, integration contract and results.
- Portable aggregate evidence includes all saved Laya screening variants and selected full runs,
  plus current scoped-permission checks; source hashes and limitations accompany the exports.
- Added a research notebook and concise reproduction/integration guides. Removed obsolete live
  legacy-provider wiring and redundant checks; retained authorization and data-integrity coverage.
- External workspace: included the architecture diagram; moved the supplied manuscript into `paper/`.
  Other repositories, third-party papers, administration files, credentials and raw logs remain local.
- Remaining before public release: author review of paper/results consistency, repository/data license
  confirmation, and recovery of missing historical sweep source if full sweep reproduction is claimed.
- Demo-software branch is planned, not created. Fine-tuning, calibration and real-user validation remain open.

## Current objective

Permission-layer update (branch `codex/scoped-permission-learning`, based on `19fe142`):
- Implemented persistent exact grants, isolated per-user contextual learning, explicit operator
  grant/revoke/review/export commands, and dispatch-time grant revalidation. Legacy counting
  and broad grants remain historical simulation comparators; live learning requires `scoped`.
- CPU regression: **362 passed**, Ruff passed. Constructed validation: 36 sequences,
  three modes, zero forbidden dispatches; final holdout satisfies 36/36 enforcement expectations per mode.
- Real pinned base Laya: **12/12 inference calls completed**, no truncation/errors; final controller
  outcomes match 10/12 constructed expectations. All three mandatory confirmations withheld dispatch
  despite raw Laya ALLOW. This is functional evidence, not independently reviewed benchmark accuracy.
- Results: `results/permission-learning/final-20261111/report.html`. Details and commands:
  [permission milestone](../archive/milestones/2026-11-permission-memory.md) and [experiment guide](../guides/experiments.md).
- Reused teammate contextual algorithms and synthetic Workspace comparisons, keeping unsafe ablations offline. Added durable prediction caching and small-run controls; real Cybersec smoke: 21/21 inputs, no errors. See the milestone for artifacts and limitations.
- Remaining: human feedback review, broader live actor/AgentDojo validation, and later Laya fine-tuning.
  No weights were trained, no actor APIs called, and nothing was pushed or merged.

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
  and [laya-permission-v1](../../experiments/reference/laya-permission-v1/README.md), 300 train (Slack, Banking) and
  150 test (Workspace) rows, 100/50 per label, exact Laya input in `context`, deterministic
  builds. Labels reviewed by Claude, not a human. CPU regression **273 passed**.
- compact_v1 Laya input (2026-11-03, branch `data/laya-permission-v1-compact`): `compact()` in
  `gatekeeper/context.py` as input profile `compact_v1`, and
  [laya-permission-v1-compact](../../experiments/reference/laya-permission-v1-compact/README.md). All 450 rows fit 1,024 tokens
  with Laya-Cybersec and pinned Laya tokenizers (max 764 context tokens); injected evidence kept in 119/119.
  CPU regression **282 passed**.
- Approval memory (2026-11-09, branch `feature/approval-memory`): counting and bandit memory behind the Wall as an
  approval-provider wrapper (judgment asks only), a live per-run hook, a rules gatekeeper and `grids memory simulate`
  for the proposal's four setups with careful and careless users. [memory-sim](../../experiments/reference/memory-sim/README.md): inside
  the Wall, questions fall from 474 to 170.5 per 1,350 actions with 1.2 attacks executed at 20% careless; without the
  Wall, class-level memory executes 96.1. Simulated users and LLM-reviewed labels; live hook not run with real models.
  CPU regression **298 passed**.
- Permission memory on laya-pairs-v1 (2026-11-09, branch `feature/permission-memory`): scoped grants (approvals only
  prompt an offer; only an explicit user grant allows) beside counting, `grants` learner in the live hook, and
  `grids permissions laya-predict | simulate`. [permission-memory](../../experiments/reference/permission-memory/README.md): real
  Laya-Cybersec (CPU, no fine-tuning) with Siddharth's rotated-options method (2026-11-10) agrees with LLM-reviewed
  labels on 59/150 (51 with a single order); Wall + Laya executes 12 harmful actions with a careful user against 123
  for Laya alone; inside the Wall, counting cuts questions 22% and grants 4%, with 1 versus 0 skipped confirmations.
  Simulated users; not a live run. CPU regression **319 passed**.

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
10. Approval memory: run the live hook with real models; make `RulesGate` selectable for live runs; let memory
    see the request (or defer to Laya) so task mismatches identical to legitimate actions are not auto-allowed;
    measure how often real actions recur before relying on the simulated reduction in questions.
11. Permission grants: an operator channel that can accept a grant scope; remembered rejections for the grant arm;
    human review of the laya-pairs-v1 labels; rerun if the team's Laya method or checkpoint changes.

Historical task details remain in Git. Retained local raw artifacts are not proof
of real-model validation of the refactor.

Release verification: Ruff passed; **352 CPU tests passed** after removing 10 redundant/obsolete checks. The documented simulated demo completed 504 actions per strategy (off, grants, active), with zero forbidden dispatches and zero errors. Evidence: `results/research-release-smoke-20261111/report.html`. No new real inference was performed during release preparation.

## Paper-style publication page — 2026-11-11

Reorganized reference datasets/historical studies into `experiments/reference`, development history into `docs/archive`, and contributor guidance into root `CONTRIBUTING.md`. Archived three redundant per-seed CSV files locally with hashes and retained Git revision. Preserved all comparison rows, including weak results, and cataloged 19 local compute summaries. The public page uses the supplied manuscript and links the gated 150-pair dataset. Added a thin demo benchmark and deterministic static site builder. Plugin files were excluded from all edits.

Verification: Ruff passed; 352 CPU tests passed in 18.42s. The new benchmark wrapper completed 504 actions per strategy with zero forbidden dispatches/errors at results/pages-demo-20261111/report.html. Local Markdown links resolved; desktop/mobile page checked. No new inference or plugin edits.

Published in `026b31d`. Pages activation remains blocked: authenticated account has push=true, maintain=false, admin=false; Pages API returned 404 and has_pages=false. Repository owner must enable main:/docs in Settings → Pages.

## Pipeline-first website � 2026-11-11

Homepage now explains the shared pipeline with a six-stage native HTML architecture, interactive illustrative approval/grant/revocation walkthrough, model rationale/configuration, dataset excerpts and contributors. Separate results page preserves all comparisons and adds local-demo-20261111-200647 and local-laya-20261111-200928 evidence (12/12 inference, 10/12 controller agreement). No new inference or plugin changes. Ruff passed; 352 CPU tests passed in 17.96s. Desktop walkthrough and mobile dataset preview checked; local page/download links resolve. Pages is now enabled on main:/docs (API status built).
