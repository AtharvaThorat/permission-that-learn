# October 2026 authorization-evaluation refactor

Branch: `refactor/authorization-evaluation`, based on `f92e51f` after fetching and
fast-forward checking `main`. No main merge or remote push is part of this task.

## Delivered

- Unified production packages under `src/grids`, with one controller and real Wall.
  Reference Wall is test-only; rules-only mode and duplicate/task-specific runners,
  wrappers, frozen panels and historical tracked reports were retired.
- Added frozen-action capture, checksummed identities, Wall-only/Laya-only/combined
  offline evaluation, independent labels and paired authorization metrics. Errors,
  missing labels and incomplete evaluations remain visible and unscored.
- Preserved native three-suite execution/scoring, exact approval binding, fail-closed
  Laya errors, scheduler limits, attempt history and live reports.
- Added five official pinned actor candidates alongside both Qwens. Model-specific
  package/parser/template settings are profiles, not permission-controller branches.
- Consolidated dependency files, one CPU CI workflow, one Slurm entry and one thin
  notebook. Reorganized docs around one index, guidelines and project tracker.

## Verification on 2026-10-29

The existing CPU environment was reused. Scripted actors and test labels are
controlled fixtures, never real-model performance evidence.

```powershell
& '.\.venv-blackbox-tests\Scripts\python.exe' -m ruff check src tests
& '.\.venv-blackbox-tests\Scripts\python.exe' -m pytest -q -p no:cacheprovider --tb=short
```

Ruff passed; final regression **262 passed in 45.45s**. Baseline: 292 passed,
1 skipped. Removed tests target retired wrappers/reports/config layouts; meaningful
enforcement/property tests remain. New checks cover frozen evaluation, per-action
state changes, independent labels, errors/missingness, CLI, Unicode identities and
all seven actor profiles. Intermediate migration failures were corrected before
the final pass, including obsolete config/model assumptions and path handling.

Focused checks establish no actor/tool calls during replay, matching context IDs,
no label leakage, failed-prediction exclusion, source immutability and no overwrite.
Installed CLI help/discovery/planning and a controlled offline HTML report are
checked outside the repository root. Seven-model, three-mode plans with one clean
task and one native attack expanded to 42 jobs per suite (126 total), without inference.
Discovery returned 40 Workspace, 21 Slack and 16 Banking tasks. Evidence lives in
ignored `tmp/refactor-cli-proof/` and CPU logs in `tmp/`. All 14 Markdown files have
valid local links; notebook code compiles with no saved outputs.
`bash -n scripts/carc_a100.sbatch` validates syntax only.

## Migration and limits

Old package names, script paths and historical schema assumptions are not compatibility
APIs. Use `python -m grids --help` and the [setup guide](../guides/setup.md).
The actor credential variable is `GRIDS_ACTOR_API_KEY`. Recollect actions: old
traces lack complete decision-time snapshots and cannot be silently converted.

Git retains retired tracked material; local results, model caches and environments
were not deleted. New research must identify source/dataset/label/model provenance.
Old task scores do not establish authorization accuracy.

No weights were downloaded, no real Laya/actor inference was run, and no Colab/CARC
session or job was started. Official metadata and vLLM parser documentation were
researched; GPU loading and memory fit remain unverified. Independent labels,
real-model regression, semantic quality and CARC site validation remain open in
the [tracker](../project_tracking.md). No task-specific security exception, automatic
ASK approval or benchmark-score tuning was introduced.
