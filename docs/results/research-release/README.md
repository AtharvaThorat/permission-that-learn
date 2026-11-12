# Research release evidence

[Readable HTML](report.html) · [Laya CSV](laya-comparison.csv) · [Permission JSON](permission-summary.json)

These are aggregate exports of existing runs, not new experiments. [Provenance](provenance.json)
records source paths and hashes. Raw local artifacts remain intact and are excluded from publication.

| Experiment | Evidence | Interpretation |
|---|---|---|
| Scoped permissions | 504 steps per strategy, 36 independent constructed sequences; zero forbidden dispatches | Functional enforcement, not human-user accuracy |
| Questions avoided | Explicit grants 29; contextual learner 9; baseline 168 questions | No demonstrated advantage of learning over explicit grants |
| Base Laya CPU smoke | 12 completed, final outcomes match 10 constructed expectations | Two conservative BLOCK/ASK disagreements |
| Laya question search | 30 screening examples per configuration; selected variants tested on 150 | Exploratory agreement with provisional labels, no independent held-out validation |

The CSV keeps all configurations, failed/unscored denominators, false approvals and compute metrics.
Option rotations are multiple questions forming one prediction, not additional independent samples.
No temperature calibration or trained candidate is claimed. Model versions and run details are
in the [permission milestone](../../archive/milestones/2026-11-permission-memory.md); screening code from
an earlier local workspace is unavailable in this checkout, so those aggregates are historical evidence.
Use the [reproduction guide](../../guides/reproduce.md) for currently executable workflows.

## Latest local checks and website

The [results page](../../results.html) distinguishes simulated learning checks from real inference. `latest-permission-check.json` records the 2026-11-11 local demo (504 actions per arm); `latest-laya-check.json` and `.csv` record all 12 real base-Laya inputs, raw predictions and final outcomes. Exports include source hashes and omit machine-local asset paths. `dataset-preview.json` contains three cached pairs with provisional source labels and review status. The browser walkthrough is illustrative only and performs no inference or dispatch.
