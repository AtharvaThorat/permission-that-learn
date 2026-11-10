# Documentation index

| Location | Contents |
|---|---|
| [PROJECT_GUIDELINES.md](PROJECT_GUIDELINES.md) | Reusable coding-agent instructions and contribution rules |
| [project_tracking.md](project_tracking.md) | Current project overview, verified progress, and remaining work |
| [architecture/system/overview.md](architecture/system/overview.md) | Package boundaries and live execution |
| [architecture/authorization/contract.md](architecture/authorization/contract.md) | Evidence, enforcement, approvals, and independent labels |
| [architecture/evaluation/method.md](architecture/evaluation/method.md) | Matched-action evaluation, identities, metrics, and limitations |
| [guides/setup.md](guides/setup.md) | Linux/Colab installation, assets, serving, and functional validation |
| [guides/experiments.md](guides/experiments.md) | Collect actions, freeze datasets, evaluate, label, and report |
| [guides/models.md](guides/models.md) | Seven pinned actor profiles and official references |
| [guides/carc.md](guides/carc.md) | Slurm batch preparation and persistent output recovery |
| [development/testing.md](development/testing.md) | Test catalog and required checks |
| [milestones/2026-10-refactor.md](milestones/2026-10-refactor.md) | Refactor decisions, migration, and validation evidence |
| [results/README.md](results/README.md) | Rules for future curated research results |
| [results/laya-permission-v1/README.md](results/laya-permission-v1/README.md) | Laya ALLOW/ASK/BLOCK fine-tuning dataset, label guide and review sheet |
| [milestones/2026-11-laya-training-data.md](milestones/2026-11-laya-training-data.md) | Training-data build, verification evidence and limitations |
| [results/laya-permission-v1-compact/README.md](results/laya-permission-v1-compact/README.md) | The same dataset compacted to fit 1,024 Laya tokens |
| [milestones/2026-11-laya-compact.md](milestones/2026-11-laya-compact.md) | compact_v1 measurement, design, verification and limitations |
| [results/memory-sim/README.md](results/memory-sim/README.md) | Approval memory simulation: four setups, careful and careless users |
| [milestones/2026-11-approval-memory.md](milestones/2026-11-approval-memory.md) | Approval memory design, live hook, verification and limitations |

Source, configuration, environment, test, and notebook directory responsibilities
are mapped in the [project README](../README.md). Generated artifacts belong in
the ignored root `results/`, not in documentation or source directories.

The former operations, reports, schemas, user_manual, and process_documentation
trees were retired. Use the destinations above; Git retains their history.
Do not recreate parallel command manuals or status reports.
