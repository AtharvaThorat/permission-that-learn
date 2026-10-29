# GRIDS — Permissions That Learn

GRIDS studies whether tool actions proposed by language models are authorized by
the user's request, policy, and verified environment evidence. It combines a
deterministic **Wall**, a **Laya Gatekeeper**, and an enforcement controller.

The primary experiment freezes proposed actions and evaluates the **same actions
and context** with Wall-only, Laya-only, and Wall→Laya. Independent human-reviewed
ALLOW/BLOCK/ASK labels are required to measure authorization accuracy. There is
no labeled benchmark yet; unlabeled runs report decisions and coverage, not accuracy.

Native AgentDojo Workspace, Slack, and Banking runs collect actions and measure
secondary task utility and attack success. Live `unprotected`, `wall_only`, and
`wall_gatekeeper` runs may produce different trajectories: their task scores are
not a matched-action authorization comparison.

## Start here

Use Python 3.12 from the repository root:

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -r environments/cpu.txt
python -m grids --help
python -m grids benchmark discover
python -m grids benchmark plan --config configs/experiments/smoke.json
python -m pytest -q -p no:cacheprovider
```

CPU installation and planning do not download model weights. Inference requires
separate environments, explicitly downloaded assets, and `--allow-models` for
benchmark/evaluation execution. See [machine setup](docs/guides/setup.md).

## Repository

| Path | Purpose |
|---|---|
| `src/grids/` | Shared controller, Wall, Laya, actors, AgentDojo, execution and evaluation |
| `configs/` | Pinned model profiles, experiment examples, permission metadata |
| `environments/` | CPU and Laya installation profiles; actor versions live in model profiles |
| `experiments/notebooks/` | Thin notebooks invoking the public CLI |
| `tests/` | Unit and integration tests, with [test catalog](docs/development/testing.md) |
| `scripts/` | Scheduler-specific shell entry points only |
| `docs/` | [Documentation index](docs/README.md), guidelines, and project status |
| `results/` | Ignored generated datasets, labels, runs, evaluations, and reports |

Seven actor profiles are provided; profile availability is not proof of successful
GPU execution or model quality. See [models and validation status](docs/guides/models.md).
AgentDojo remains pinned to the inspected revision; an upgrade is a separate task.

Development starts with [PROJECT_GUIDELINES](docs/PROJECT_GUIDELINES.md).
This refactor intentionally replaces the former package names and CLI. Historical
tracked material is available in Git; local raw results and caches are preserved.
