# November 2026 approval memory

Branch: `feature/approval-memory`, based on `main` at `a4af015`. No merge into `main`.

## Request

Atharva Thorat (2026-11-09): implement the proposal's third layer, approval memory. It should learn from the user's
answers so that later similar actions are decided without asking, stay inside the Wall, start with counting and add
a contextual bandit. It should be evaluated in the proposal's four setups with careful and careless users. Scope
chosen: an offline simulator plus a live hook, with a deterministic rules gatekeeper as the stand-in for Laya.

## Delivered

- `src/grids/core/permissions/memory.py`:
  - `pattern_key`, with `exact` and `class` granularity, scoped by policy version;
  - `CountingMemory`: allows after k approvals, blocks after r rejections, and forgets unused patterns after a TTL;
  - `BanditMemory`: Beta Thompson sampling with a cost threshold and exploration;
  - `MemoryApprovalProvider`.

  The provider wraps any `ApprovalProvider`, so the controller is unchanged. The controller reaches it only after a
  Wall PASS and a gatekeeper result that is not BLOCK. Memory answers and learns only judgment asks
  (`NEEDS_CLARIFICATION`, `UNCERTAIN`). Forced asks always go to the user. It learns only from an `ApprovalEvent`
  whose answer is bound to the pending action. A remembered answer is an ordinary bound `ApprovalEvent`, so the
  single-use ledger and the executor's Wall recheck still apply.
- `LearningConfig` in `core/config.py` and an optional `learning` field on run specifications. While learning is
  disabled, the field is left out of the specification, so existing run identities do not change.
- Live hook (`runs/runtime.py`, `runs/services.py`):
  - one memory per run, shared by its `wall_gatekeeper` episodes under a lock;
  - each episode writes `memory.jsonl` (source `user` or `memory`, the pattern key and the answer) and
    `memory-policy.json`.
- `src/grids/gatekeeper/rules.py`: a deterministic rules gatekeeper. Reads are allowed, destructive actions are
  blocked, and anything else is asked. The simulator uses it. `RulesGate` has the gatekeeper interface but is not
  yet selectable in live runs.
- `src/grids/evaluation/memory_sim.py` and `grids memory simulate`: the offline simulator.
- [`docs/results/memory-sim/`](../results/memory-sim/README.md): the curated 50-seed run.
- `tests/unit/core/test_memory.py` (16 tests). `test_config_lifecycle.py` now uses a non-boolean value as its
  invalid `learning_enabled` example.

## Verification on 2026-11-09

```bash
python -m ruff check src tests
python -m pytest -q -p no:cacheprovider
python -m grids memory simulate --seeds 50 --passes 3 --output results/memory-sim/run_01
python -m grids memory simulate --seeds 50 --passes 3 --output results/memory-sim/run_01_check
cmp results/memory-sim/run_01/summary.csv results/memory-sim/run_01_check/summary.csv   # and the other three files
git diff --check
```

- Tests: **298 passed** and Ruff passed. The new tests cover:
  - the controller path: two user approvals, then a memory allow, with three executions;
  - tightening after a rejection;
  - no memory contact on a Wall DENY;
  - forced asks always reaching the user;
  - forged events not being learned;
  - pattern-key scope and TTL;
  - bandit seeding;
  - the specification identity when learning is disabled;
  - the runtime wrapper;
  - simulator determinism and invariants;
  - the learner receiving only keys and answers.
- The simulation reruns were byte-identical.
- Simulator sanity checks:
  - with no protection, every BLOCK row and attack executes;
  - fixed rules never auto-allow;
  - inside the Wall, memory only sees Wall-PASS actions.

## Limitations

- **Live hook.** It is CPU-tested through controller fixtures only. No real model run was made with learning
  enabled. With parallel episodes, the order in which memory learns depends on scheduling.
- **Memory scope.** Memory is held in process for one run. It is not persisted across runs or users.
- **Evidence for the findings.** The results come from simulated users on LLM-reviewed labels, with the rules
  stand-in instead of Laya, and depend on actions recurring over three passes. See the results README.
- **Action-keyed memory** cannot separate a harmful task mismatch from the identical legitimate action. That needs the
  request, which is the gatekeeper's job.
