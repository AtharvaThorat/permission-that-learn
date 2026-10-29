# Project guidelines

Use these instructions for coding agents and contributors. Read this file,
[project_tracking.md](project_tracking.md), and the relevant architecture/guide
before editing. Follow the user's approved scope; do not replace it with a new roadmap.

## Workflow

1. Check `git status --short`, applicable `AGENTS.md`, and the active branch.
2. Fetch upstream before work. On a clean starting checkout, pull `main` with
   `--ff-only`, then create a task branch. When resuming, compare the task branch
   with updated `origin/main`; preserve local work and report any integration blocker.
3. Inspect existing code and tests. State the modules to change, then implement.
4. Run focused checks and the relevant CPU regression suite; inspect the diff.
5. Update the tracker with a short status outline and one relevant milestone with
   commands, actual evidence, and remaining limitations. Update guides when commands change.
6. Commit on the task branch. Do not push without authorization. Never merge into
   local or remote `main`; the user reviews and merges through a PR. No force reset,
   history rewriting, or deletion of unrelated local artifacts.

## Architecture and research invariants

- Production Python belongs in `src/grids/`: `actors`, `benchmarks/agentdojo`,
  `core`, `wall`, `gatekeeper`, `runs`, `evaluation`, and `cli`. One shared controller
  and one production Wall; no competing runners or task-specific bypasses.
- Primary accuracy uses frozen identical action/context observations and independent
  reviewed labels. AgentDojo scores, attack labels, Wall outputs, and Laya outputs
  are not authorization ground truth. Report unlabeled data as unscored.
- Preserve native AgentDojo tasks, tool arguments, environments, attacks, and scoring.
  Benchmark utility/attack success are secondary; never tune to a task ID or score.
- Authorize before dispatch. Bind exact tool, arguments, resource/recipient evidence,
  schema, policy, state, and expiration. Revalidate before execution and reject replay.
- ASK withholds execution; never auto-approve. Model errors, missing evidence, and
  truncation are explicit and fail closed. Never fall back to unprotected execution.
- Keep raw model predictions separate from controller decisions. Preserve missing
  metrics, attempt history, paired identities, and error outcomes. Never select the best retry.
- A restarted episode is not continuation of a pending action. Human feedback can
  execute only in the original live process while the binding remains valid.

## Organization and coding

- Follow the [documentation index](README.md). Root docs contain only the index,
  this prompt, and the project tracker. Architecture, guides, tests, milestones,
  and curated results each have one authoritative home.
- Tests go in `tests/unit` and `tests/integration`, fixtures in `tests/fixtures`;
  document meaningful coverage in `docs/development/testing.md`.
- Notebooks go in `experiments/notebooks` and call the CLI; no copied runtime code.
- Configurations go in `configs/`; dependency profiles in `environments/` and
  `pyproject.toml`. Actor-specific package versions belong in `configs/models/`.
  Do not scatter requirements files, Markdown, or one-off scripts in the root.
- Generated runs/datasets/reports go in ignored `results/`; temporary work in `tmp/`.
  Curated summaries may go in `docs/results/<experiment>/` with provenance.
- Use relative repository paths in documentation. Do not commit private machine paths,
  credentials, caches, weights, environments, or unreviewed raw traces.
- Prefer concise functions, existing contracts, and comments explaining non-obvious
  decisions. Remove dead code deliberately; do not rewrite working modules for style.
- Serialize identities deterministically, including sets. Validate inputs strictly;
  surface failures rather than returning success-shaped placeholders.
- Add tests for meaningful behavior and security boundaries, not redundant wrappers
  or historical file layouts. Keep the single CPU CI workflow useful and offline.

## Verification

Run `python -m ruff check src tests`, focused tests, and `python -m pytest -q
-p no:cacheprovider` after integration changes. No models or network calls in CPU
tests. Separate controlled fixtures, real Laya inference, actor serving, and native
end-to-end evidence. Never claim GPU compatibility, model quality, authorization
accuracy, or resolved truncation based only on CPU fixtures.
