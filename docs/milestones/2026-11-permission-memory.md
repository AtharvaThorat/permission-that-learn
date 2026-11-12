# November 2026 permission memory (grants versus counting)

## 2026-11-11: persistent scoped permissions and contextual learner

Implementation branch: `codex/scoped-permission-learning`, based on fetched feature commit
`19fe142`. Earlier sections describe historical experiments; the production path below
supersedes their live counting/broad-grant hooks. No main merge or push.

### Delivered

- SQLite schema v1: user-scoped exact grants, expiring/use-limited reservations, decisions,
  learner parameters/RNG, reviewed feedback, and transactional audit events. No auto-grants.
- Existing controller/ledger/executor retain exact action, state, policy and schema checks.
  Grant use adds user/grant/version binding, durable reservation, session binding, and a
  dispatch guard serialized with revocation. Expiry is checked again after final audit.
  Failed/uncertain reservations are never recycled; old-process reservations cannot execute.
- `ScopedApprovalProvider` is connected through the existing run services. Live learning
  requires `learner: scoped`, trusted `user_id`, and `store_path`. Counting/bandit and broad
  grants remain available for historical simulations. Default learning mode is shadow.
- Contextual epsilon-greedy linear cost estimates use Laya probabilities, tool/effects,
  trusted metadata category, grant age, and reviewed history count. Parameters/RNG are
  separate per user. Epsilon .1, seed 42, initial ten eligible asks, learning rate .05;
  ASK cost 1, reviewed acceptable/unwanted grant reuse cost 0/10. Unknown reuse gets no reward.
- Explicit grant/list/revoke and reviewed-feedback/export CLI operations; one-action approval
  stays separate. Review must verify request/policy/outcome and include consent before training
  export. No Laya weights changed and no automatic checkpoint promotion.
- Deterministic 36-sequence generator: twelve per suite and twelve initial expectations per
  class. Fourteen steps per sequence (initial, twelve training, frozen holdout); three strategies
  receive identical actions/context. User-1 reports unwanted reuse; other synthetic users accept it.
  These expectations and preference reviews are constructed fixtures, not human annotations.

### Executed evidence

```powershell
& tmp/permission-tests/Scripts/python.exe -m pytest -q -p no:cacheprovider --tb=short
& tmp/permission-tests/Scripts/python.exe -m ruff check src tests
$env:PYTHONPATH='src'
& workspace/.venv/Scripts/python.exe -m grids permissions check --output results/permission-learning/final-20261111 --real-laya --cache workspace/cache
# Report regeneration uses saved output only:
& workspace/.venv/Scripts/python.exe -m grids permissions report --run-dir results/permission-learning/final-20261111
```

The isolated test environment was installed with `python -m pip install -e '.[test,benchmark]'`;
the existing Laya environment was preserved. **362 CPU tests passed**, Ruff passed.
The new scoped-permission module contains 34 focused tests, including race/expiry/storage failures,
restart/replay, exact scope, consent, isolated learning, and report regeneration.

| Strategy | Actions | Questions | Questions saved | Forbidden dispatches |
|---|---:|---:|---:|---:|
| No memory | 504 | 168 | 0 | 0 |
| Explicit grants | 504 | 139 | 29 | 0 |
| Grants + contextual learner | 504 | 159 | 9 | 0 |

Each strategy satisfies 36/36 final holdout enforcement expectations: 12 ALLOW, 12 ASK, 12 BLOCK.
A valid grant may satisfy an optional ASK without another question. Repeated steps are learning
interactions, not independent accuracy samples. These results do not show the learner outperforming grants.

Real CPU smoke: base `convaiinnovations/laya@7b928d828b7b0e022f929d9bd2e44165aa270148`,
single-v1, original 512-token checkpoint limits, four threads. **12/12 evaluations completed**,
no errors/truncation. The adapter also performs one initialization warm-up. Packages: Laya 0.3.28,
torch 2.15.0+cpu, transformers 5.22.2. Final controller outcomes match **10/12** constructed
expectations (ALLOW 3/3, ASK 4/6, BLOCK 3/3); raw intent agreement is separately 10/12.
The three mandatory-confirmation cases had raw Laya ALLOW but no dispatch. Two wait-for-confirmation
examples received conservative BLOCK instead of ASK. No outputs were replaced with fixture predictions.

Measured final smoke: initialization including warm-up 4.68s; twelve evaluations 11.51s total;
sampled process-tree CPU 55.5 CPU-seconds including initialization; peak summed RSS 2.76 GB
(decimal). Timings include concurrent CPU regression activity and are functional measurements,
not a controlled performance comparison. The checkpoint emitted an upstream temperature-clamping
warning; confidence is not claimed to be calibrated.

Artifacts are local/ignored: `results/permission-learning/final-20261111/` contains `report.html`,
`actions.csv`, `actions.jsonl`, `scenarios.json`, each strategy's SQLite store, `run.json`,
`summary.json`, `laya.csv`, `laya.jsonl`, and `laya-summary.json`. An earlier validation run is
preserved at `results/permission-learning/validation-20261111/`. Across both smoke runs,
24 examples were evaluated plus two initialization warm-ups; no actor/API calls were made.

### Limits and next work

- Local trusted-operator interface only; no remote authentication or multi-tenant service.
- Exact grants deliberately invalidate on context changes; no wildcard/class generalization.
- SQLite holds a write transaction through dispatch; concurrent writers can time out safely.
  A crash preserves consumed reservations; actual external side effects are never automatically retried.
- Fine-tuning, original-data retention, frozen human-reviewed evaluation, injection regression gates,
  explicit checkpoint promotion and rollback remain the next milestone. This delivery only collects
  reviewed training candidates. A reviewer must independently assess source policy and intent.
- No native live actor benchmark, CARC submission, GPU validation, or model-quality claim.
- Reproduction and review/export formats: [experiment guide](../guides/experiments.md#scoped-permission-learning-local-research).

## Historical implementation and experiments

Branch: `feature/permission-memory`, from local `feature/approval-memory` (`96cd6db`, from `main` at `a4af015`).
Not pushed. No merge into `main`.

## Request

Atharva Thorat (2026-11-09):
- Siddharth Magesh's gated `siddharth-magesh/grids-laya-permission-v1` (150 adapted pairs) is now the team dataset.
- The permissions research and a basic implementation are Atharva's part.
- The team suggested "grants, not counts", and Atharva chose to compare grants and counting.
- Steps: read the dataset, write a research note, design, implement, run an exploratory evaluation, and write paper
  input. Learning stays outside the A/B/C AgentDojo benchmark.

## Delivered

- `GrantStore` and `GrantApprovalProvider` (`core/permissions/memory.py`):
  - approvals are statistics that only prompt an offer;
  - only an explicit user grant (exact or trust-class scope, policy version in the key, optional expiry) answers an
    ask;
  - a rejection revokes the grant.

  `LearningConfig.learner` accepts `grants`, and `runs/runtime.py` selects the grant provider.
- `src/grids/evaluation/permission_sim.py` with `grids permissions laya-predict | simulate`:
  - real Laya-Cybersec predictions on the pairs (CPU, recorded once);
  - the live decision order;
  - no memory, counting (exact and class) and grants;
  - each with and without the Wall, with the Laya and rules gatekeepers, and under two label sets.
- [Research note and design](../architecture/authorization/permission-memory.md).
- [`docs/results/permission-memory/`](../results/permission-memory/README.md): reviewed labels, Laya predictions,
  curated run and findings.
- `tests/unit/core/test_permission_grants.py` (11 tests).

## Verification on 2026-11-09

```bash
python -m ruff check src tests
python -m pytest -q -p no:cacheprovider
# Laya environment, CPU, twice: identical decisions and probabilities
python -m grids permissions laya-predict --pairs <pairs> --metadata <metadata> --output results/permission-memory/laya_cybersec_predictions.jsonl
# twice into new directories: byte-identical files
python -m grids permissions simulate --pairs <pairs> --seeds 50 --passes 3 --output results/permission-memory/run_01
git diff --check
```

- **Tests:** 309 passed and Ruff passed. The grant tests cover:
  - approvals alone never authorize;
  - the Priya scope example (another person, another tool and a new policy version are not covered);
  - class scope stays within its class;
  - revocation and expiry;
  - controller runs with and without an accepted offer;
  - no contact with Wall denials or forced asks;
  - runtime selection;
  - the simulator's live decision order;
  - careful grants never skipping confirmations where counting does;
  - the published files.
- **Loader check:** all 150 pairs matched their source action exactly.
- **Laya-Cybersec** (`41fd5a2`, laya 0.3.28, torch 2.14.1, transformers 5.20.2, CPU): 150/150 rows without error,
  about 0.1 s per row. The release metadata records transformers 5.22.2; the repo pin 5.20.2 was used here.

## Update 2026-11-10: rotated Laya-Cybersec options

Siddharth Magesh asked for Laya-Cybersec (`41fd5a2`, as released) with rotated decision options: the dataset's
question and criteria are kept, and three option orders, (ALLOW, ASK, BLOCK), (ASK, BLOCK, ALLOW) and
(BLOCK, ALLOW, ASK), are asked in one model call. All answers and truncation diagnostics are validated, the
probabilities are averaged by label, the highest average wins and a tie returns ASK.

- `grids permissions laya-predict --method rotated` (now the default) implements it; `--method single` keeps the
  first run's behaviour. `simulate --predictions` selects the recorded predictions.
- `laya_cybersec_rotated_predictions.jsonl` was recorded twice on CPU with identical decisions and probabilities.
  150/150 rows, no errors or truncation. The (ALLOW, ASK, BLOCK) answer equals the single-order run exactly.
- The curated simulation is now run_02 on the rotated predictions, run twice with byte-identical files.
- Findings changed: rotation gives 92 ALLOW, 10 ASK and 48 BLOCK, agreement 59/150 with the reviewed labels, and 41
  of 78 harmful rows allowed (29 before). Inside the Wall, memory saves 22% (counting) and 4% (grants) of questions,
  since few gatekeeper asks remain.
- Tests: 10 new (option rotation, averaging, tie to ASK, fail-closed validation, published predictions).

## Limitations

- Labels are LLM-made:
  - the reviewed labels are Claude's re-judgment of the adapted prompts;
  - the source labels are the release's provisional labels;
  - they differ on 34 rows.
- Wall facts are replayed from the original native context, not derived from the adapted free-text policies.
- Simulated users only. Repetition is a 3-pass assumption.
- Live grants:
  - the hook is CPU-tested only;
  - the file operator channel cannot issue grants, so live runs only log offers;
  - no live run with learning enabled was made.
- The dataset itself is gated and not committed. Its sha256 is recorded.

## Teammate integration verified 2026-11-11

Selectively reused `AtharvaThorat/permission-that-learn@736648230eaefec916873f922a1d560dbb160d5a`:
`contextual.py`, `synthetic_users.py`, `learning_sim.py`, `learning_data.py`, `learning_cli.py`,
reusable prediction helpers, and scope-revocation fixes. No branch merge. Live learning retains
our SQLite exact-grant provider; the teammate's free/pooled/class-scope arms stay offline.

Added small-cohort options, explicit worker limits and sweep opt-out. Prediction files retain raw
order probabilities, flush each result, record initialization failures and local checkpoint hashes,
reject duplicates/mismatched overwrites, and reuse complete matching caches without inference.
Fixed Windows newline-dependent synthetic-file hashes. The pre-fix smoke's `spec.json` hashes
represent LF text, while its prediction header records actual file-byte hashes; originals are retained.

Verification: **362 CPU tests passed**, Ruff passed. This includes 34 scoped-permission tests and
9 contextual-policy/artifact tests. The real offline Cybersec workflow completed **21/21** inputs
(12 stream, 6 eval, 3 canary), zero errors, 8 ALLOW/13 BLOCK/0 ASK, 24.329s summed inference latency.
Checkpoint `41fd5a2dfced0fb357974afd780a3ed6e7c43838`; Laya 0.3.28, torch 2.15.0+cpu,
transformers 5.22.2, CPU four threads. A one-seed comparison with one worker and no sweep completed.
This tiny smoke tests compatibility, not learning benefit or model quality; the stream is shorter
than the simulator's cold-start period. No training, actor APIs or full benchmark was run.

Evidence: `results/permission-learning/integration-world-20261111/`,
`integration-predictions-20261111.jsonl`, and `integration-comparison-20261111/` under the same
permission-learning directory. The earlier three-suite HTML remains `final-20261111/report.html`.
Commands are in the [experiment guide](../guides/experiments.md#offline-contextual-policy-comparisons).

The installed Laya exposes `TrainConfig`, `dry_run`, and `finetune` with encoder freezing and
option shuffling, but training compatibility has not been exercised. Fine-tuning, calibration,
poison-resistant label verification, frozen promotion gates and real-user validation remain open.
The teammate's reported 4,800-action findings were not rerun or adopted as our own measurements.
