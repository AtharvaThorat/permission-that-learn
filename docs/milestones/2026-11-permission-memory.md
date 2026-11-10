# November 2026 permission memory (grants versus counting)

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
