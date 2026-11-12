# November 2026 Laya fine-tuning data

Branch: `data/laya-permission-v1`, based on `main` at `19ca760` after fetching and a
fast-forward check. No merge into `main`; review and merge through a PR.

## Request and decisions

Siddharth Magesh asked (2026-11-01) for `train.jsonl` (300 rows) and `test.jsonl` (150 rows),
100/50 per label, with fields `id, prompt, label, source, source_id, group_id, context`, for
fine-tuning Laya on ALLOW/ASK/BLOCK. The original plan took ALLOW/BLOCK from
neuralchemy chat prompts and ASK from AgentDojo. Laya never sees chat prompts, and mixed
sources let a model learn the source instead of the decision, so Siddharth chose (2026-11-02)
that every row is an agent action in Laya's input format, with neuralchemy text used only as
injected content.

- `context` is the exact canonical evidence_v2 state string Laya receives in `laya_only` form
  (`wall` null), built through `evaluation.replay.reconstruct` and `request_for`. A string,
  not a nested object, because states differ in structure and types across rows.
- Train is Slack and Banking, test is Workspace (an unseen suite). Travel is excluded because
  the Wall and frozen-action schema do not support it.
- Rows: original ground-truth calls; LLM-drafted rewritten requests with their own labels
  (`configs/datasets/laya-permission-v1/prompt_variants.json`); injected-goal BLOCK; task-mismatch
  BLOCK. Injected histories appear in every label, attacker identities are randomized, and
  short ALLOW/BLOCK plus long ASK requests keep prompt length from predicting ASK.
- Labels were reviewed by Claude (an LLM), not a human. The README states this.

## Delivered

- `src/grids/gatekeeper/training_data.py` and `grids training-data fetch|extract|candidates|review|finalize|validate`.
- `training-data` extra in `pyproject.toml` and `environments/training-data.txt`.
- `experiments/reference/laya-permission-v1/`: `train.jsonl`, `test.jsonl`, `README.md` (dataset card
  with file hashes), `provenance.jsonl`, `label_guide.md`, `review.csv`.
- `tests/unit/core/test_training_data.py` (11 tests).

## Verification on 2026-11-02

macOS, Python 3.12, repository `.venv` from `environments/cpu.txt` plus the training-data pins.
CPU only; no model was loaded.

```bash
python -m grids training-data fetch
python -m grids training-data candidates
python -m grids training-data review
python -m grids training-data finalize --reviewer "Claude (an LLM, Anthropic), not a human"
python -m grids training-data validate
python -m ruff check src tests
python -m pytest -q -p no:cacheprovider
git diff --check
```

- `validate`: valid. 300 train and 150 test rows, exactly 100/50 per label; canonical contexts
  matching each prompt; unique ids, source ids and contexts; no prompt and action pair with two
  labels; no label word in any context; no shared `group_id` or near-duplicate prompt across
  splits; both files load with `datasets`.
- Review: 536 candidates, 530 agreed, 6 dropped with notes. The review rules are encoded in the
  builder, so no row needed relabeling.
- Determinism: candidates rebuilt under `PYTHONHASHSEED` 1, 987 and 4242 are byte-identical.
- Prompt-length shortcut: a length-only ASK-vs-rest classifier reaches 0.70 (train) and 0.69
  (test), against 0.67 for always predicting "not ASK". Before balancing it reached 0.77.
- Ruff passed; 273 tests passed (262 before this task plus 11).

## Findings outside this task

- **Nondeterministic identity serialization.** `PtlWall` trusted identities and policy grants hold
  frozensets, and `model_dump` emits them in per-process hash order. For Slack `user_task_0`,
  `digest(wall.context.model_dump(mode='json'))` was `70b1e1c1f0f0` under `PYTHONHASHSEED=1` and
  `7c257c8732d0` under `2`. This affects `permission-context.json`, frozen-dataset `context_id`
  values and the live Laya input string. `CONTRIBUTING.md` requires deterministic set
  serialization. The builder sorts these lists itself; the production fix is a separate task.
- AgentDojo stamps created files and sent emails with the wall clock. The builder pins it to
  2024-05-15 12:00, the Workspace suite's own current day.

## Limitations

- Labels are LLM-reviewed only, with no agreement measure. People should relabel at least the
  test split before any reported accuracy.
- Most ASK rows are rewritten requests of fully specified AgentDojo tasks.
- Workspace injection tasks 6 to 13 have no executable ground truth at the pinned revision.
- Rows over 24,000 characters were dropped, not truncated.
- Fine-tuning itself and any real Laya inference on this data were not run here.
