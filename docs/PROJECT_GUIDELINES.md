# Project Development Guidelines

These guidelines apply to coding agents and contributors working on the GRIDS /
Permission That Learns repository. The goal is to preserve a clean,
traceable, reproducible codebase while extending the existing evaluation
platform.

## 1. Development workflow

1. Start from an up-to-date local `main` branch.
2. Create a focused feature or fix branch:

   ```powershell
   git switch main
   git pull --ff-only
   git switch -c <short-purposeful-branch-name>
   ```

3. Inspect the relevant implementation, tests, configuration, and
   documentation before editing.
4. Make the smallest complete change that addresses the task.
5. Run focused tests first, then the smallest applicable broader suite.
6. Run formatting, lint, type, or link checks required by the changed area.
7. Review the diff for accidental files, generated artifacts, secrets, and
   unrelated edits.
8. Commit with a clear message. Do not rewrite existing history or use
   destructive reset/clean commands.
9. Merge the reviewed branch into local `main` using a fast-forward or normal
   merge as appropriate. Do not force-merge.
10. Push only when explicitly authorized by the repository owner.

Keep branches focused. Do not combine unrelated refactors, documentation
reorganization, dependency changes, and feature work in one branch unless the
task explicitly requires them.

## 2. Code quality and style

- Preserve the existing architecture, naming, formatting, and helper patterns.
- Prefer concise, readable, structured code over clever or duplicated logic.
- Fix the root cause rather than adding a workaround or weakening an assertion.
- Keep functions and modules focused on one responsibility.
- Preserve type safety and use existing types, guards, and validation helpers.
- Do not add broad exception handlers, silent fallbacks, or success-shaped
  results for invalid or failed operations.
- Surface errors explicitly with the repository's established error and logging
  conventions.
- Do not silently fall back from a protected execution mode to an unprotected
  mode.
- Do not replace missing metrics with zero or overwrite prior attempts.
- Add comments only when they explain non-obvious behavior.
- Avoid unnecessary dependencies, abstractions, generated code, and unrelated
  formatting changes.
- Never commit credentials, tokens, model weights, private endpoints, or other
  secrets.
- Anything hashed into an identity, fingerprint, digest, or `pair_id` must
  serialize deterministically. Sort sets and frozensets before dumping; never
  depend on `PYTHONHASHSEED` or set iteration order. Test such values across
  separate processes, not only within one.

Before adding a helper or abstraction, search for existing prior art. Reuse
shared contracts and utilities where possible.

## 3. Directory responsibilities

| Directory | Responsibility |
|---|---|
| `blackbox/` | Core actor, controller, contracts, execution, audit, configuration, and permission integrations. |
| `integrations/agentdojo/` | AgentDojo-native pipeline, task/tool mapping, workspace facts, codecs, and runners. |
| `wall/` | The standalone `ptl.wall` package, policy/context models, harness integration, and its package tests. |
| `gatekeeper/` | Existing Laya gatekeeper configuration, schemas, prompts, adapter, lifecycle, and policy logic. |
| `experiment/` | Experiment specifications, deterministic planning, runtime execution, scheduling, persistence, aggregation, comparison, replay, and CLI. |
| `configs/` | Explicit configuration examples and environment/task metadata. Keep local secrets in ignored local files. |
| `tests/blackbox/` | Black-box contracts, runtime, actor, pipeline, configuration, and AgentDojo-facing tests. |
| `tests/evaluation/` | Evaluation-platform tests for planning, scheduling, storage, runtime modes, aggregation, and replay. |
| `wall/tests/` | Wall unit, property, contract, harness, and policy fixture tests. |
| `scripts/` | Operational setup, benchmark, serving, replay, and static-check scripts. |
| `docs/architecture/` | Architecture, contracts, code maps, and compatibility/reference material. |
| `docs/operations/` | Setup, execution, Colab, benchmark, and operational runbooks. |
| `docs/reports/` | Implementation, readiness, and status reports. |
| `docs/benchmark-results/` | Historical benchmark and experiment result reports. |
| `docs/schemas/` | Machine-readable schemas used by the platform or documented artifacts. |
| `results/` | Generated local experiment output; do not commit runtime results unless explicitly requested. |

Do not place ad hoc notes, reports, test output, or planning files in the
repository root or random source directories. Put durable documentation in the
appropriate `docs/` category and temporary artifacts in an ignored workspace
location.

## 4. Documentation rules

- Update documentation when behavior, configuration, CLI commands, output
  schemas, supported modes, or operational requirements change.
- Edit the existing document responsible for the topic instead of creating a
  second overlapping document.
- Add a new document only when the content has a distinct long-term purpose.
- Add every new durable document to [the documentation index](README.md).
- Keep architecture, operations, reports, results, and schemas in their
  respective directories.
- Update relative links whenever files are moved.
- Do not present CPU tests, synthetic fixtures, or static inspection as proof
  of real-model utility, attack success, GPU performance, or Laya runtime
  compatibility.
- Mark historical results as historical and distinguish them from current
  instructions.
- Keep reports concise and evidence-based. Record exact commands and actual
  results rather than estimated outcomes.

## 5. Test creation and maintenance

Every behavior change should have a focused test unless it is genuinely
untestable and the reason is documented.

Tests should:

- be deterministic and isolated;
- use scripted actors, CPU fixtures, temporary directories, and local fakes
  where possible;
- avoid network access, model downloads, GPU inference, and external services
  by default;
- verify observable behavior and required output shapes;
- test failure paths, missing data, retries, cancellation, and state isolation
  where relevant;
- avoid weakening assertions to accommodate an implementation defect.

Use the existing test location that matches the changed component. Do not
duplicate the same test in multiple directories. Remove a test only when it is
unreachable, redundant, obsolete because the tested behavior was intentionally
removed, or replaced by a more complete test. Before removing it, search for
references and confirm that it is not used by CI, scripts, packaging, or
documentation.

Fixtures that stand in for external assets (model snapshots, AgentDojo data,
endpoint responses) must mirror the real layout and format. Check the fixture
against the real asset listing once and note the source in the test. A
validator that only passes on a hand-made fixture is not verified.

Do not commit `__pycache__`, `.pytest_cache`, logs, model artifacts, generated
results, or temporary files.

## 6. Experiment and result requirements

Experiment changes must preserve reproducibility and provenance. Record the
experiment identity, configuration, model/actor profile, mode, task, attack,
seed, repetition, attempt, lifecycle, and relevant runtime versions.

Result handling must:

- use unique job and attempt identities;
- preserve completed, failed, interrupted, and pending states;
- avoid overwriting earlier attempts;
- retain raw evidence separately from summaries;
- keep unavailable metrics missing rather than converting them to zero;
- make aggregation policy explicit;
- validate identities before paired comparisons;
- write machine-readable JSON and tabular CSV where the existing workflow
  expects both;
- keep replay output separate from source artifacts.

The acting-model server and the experiment runner use separate Python
environments: vLLM 0.11.0 needs `transformers==4.57.1`, while the runner hosts
the Laya worker and needs the pinned Laya stack (`torch==2.14.1`,
`transformers==5.19.0`). They communicate only over the local HTTP endpoint.
`notebooks/person3_protected_smoke_test.ipynb` shows the working Colab setup.

Do not run real models or external inference as part of ordinary unit-test
validation. Real-model execution requires explicit authorization, a documented
configuration, controlled resource limits, and a separate report of actual
resource usage and failures.

## 7. Validation checklist

Before requesting review:

```powershell
git diff --check
git status --short
```

Run the narrowest relevant tests first. For changes spanning the black-box,
wall, or evaluation platform, run:

```powershell
& '.\.venv-blackbox-tests\Scripts\python.exe' -m pytest -q -p no:cacheprovider
```

For documentation-only changes, check all changed relative links and confirm
that no source or test files were modified unintentionally.

Review the final diff and confirm:

- only intended files changed;
- no secrets or generated artifacts are included;
- documentation links resolve;
- tests cover the changed behavior;
- limitations and unverified runtime claims are stated accurately;
- the working tree is clean after commit.

## 8. Review and merge expectations

A change is ready to merge only when its implementation, tests, configuration,
and documentation agree. Reviewers should reject changes that:

- create duplicate documentation instead of updating the correct document;
- add tests that only assert implementation details without behavior coverage;
- silently hide errors or failed experiment attempts;
- alter wall or permission semantics merely to make a test pass;
- mix unrelated cleanup into a feature fix;
- claim real-model or AgentDojo validation without recorded execution evidence.

