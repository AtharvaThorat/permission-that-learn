<div align="center">

# Permissions That Learn

### Policy-bounded authorization for tool-using language model agents

*Research project with Graduates Rising in Data Science, a student club at the University of Southern California (USC).*

[![Authorization](https://img.shields.io/badge/Authorization-Wall%20%2B%20Laya-438cbf?style=for-the-badge)](#how-the-pipeline-works)
[![Learning](https://img.shields.io/badge/Learning-Scoped%20grants-2ea44f?style=for-the-badge)](#implementation)
[![Evaluation](https://img.shields.io/badge/Evaluation-AgentDojo-d4b83f?style=for-the-badge)](#research-results)
[![License](https://img.shields.io/badge/License-Apache%202.0-91cf60?style=for-the-badge)](LICENSE)

[**Research page**](https://AtharvaThorat.github.io/permission-that-learn/) · [**Dataset**](https://huggingface.co/datasets/siddharth-magesh/grids-laya-permission-v1) · [**Paper**](paper/manuscript.pdf) Â· [**Results**](docs/results/research-release/README.md) Â· [**Demo**](#demonstration)

</div>

## Contents

- [Research idea](#research-idea)
- [How the pipeline works](#how-the-pipeline-works)
- [Implementation](#implementation)
- [Research results](#research-results)
- [Demonstration](#demonstration)
- [License and acknowledgment](#license-and-acknowledgment)
- [Authors](#authors)

## Research idea

Tool-using agents can propose actions that exceed the user's request or trusted permissions. This project explores an authorization layer that evaluates each proposed action before execution, combining deterministic policy enforcement with contextual model decisions and carefully scoped permission learning.

The primary question is whether the system makes the right **ALLOW**, **ASK**, or **BLOCK** decision for a proposed action and its evidence. We measure authorization decisions and inference cost alongside AgentDojo's native task utility and attack success. Task completion alone does not establish that an action was authorized.

## How the pipeline works

```mermaid
flowchart LR
    U[User request] --> A[Acting agent proposes tool action]
    A --> B[Parse and bind exact arguments]
    B --> W{Deterministic Wall}
    W -->|Deny or unresolved| X[Withhold or escalate]
    W -->|Pass| L{Laya Gatekeeper}
    L -->|BLOCK or error| X
    L -->|ALLOW| R[Recheck action and context]
    L -->|ASK| P[Explicit approval or matching scoped grant]
    P --> R
    R -->|Checks pass| T[Dispatch exact action]
    T --> A
```

The Wall applies fixed capability, resource, recipient, policy, and state checks. Laya evaluates whether the action follows the authentic request using trusted evidence. An ASK withholds the action for approval; a reusable grant must match its exact scope and remain valid. Before dispatch, the controller verifies the same action, state, policy, schema, and grant. Learning cannot override a Wall denial, mandatory confirmation, or Gatekeeper BLOCK.

## Implementation

One Python package and CLI provide the shared controller for native AgentDojo **Workspace**, **Slack**, and **Banking** tasks. The runner supports `unprotected`, `wall_only`, and `wall_gatekeeper` modes, with actor profiles for model-specific serving and tool parsing.

The implementation is organized around a few components:

- `src/grids/actors/` connects acting models through reusable clients and profiles.
- `src/grids/benchmarks/agentdojo/` adapts native tasks, tools, context, and scoring.
- `src/grids/wall/` evaluates deterministic permissions from trusted facts.
- `src/grids/gatekeeper/` prepares evidence for Laya and validates its decisions.
- `src/grids/core/` binds actions, requests approval, and gates tool dispatch.
- `src/grids/evaluation/` captures actions, replays identical inputs, and computes research metrics.
- `src/grids/runs/` schedules episodes and stores traces, attempts, and reports.

The same controller can be used by another application through its actor, tool-runtime, and trusted-facts interfaces. See the [integration guide](docs/guides/integration.md) and [documentation index](docs/README.md).

## Research results

The [results page](docs/results/research-release/README.md) provides the saved HTML report, CSV comparisons, JSON summaries, and source provenance. The evidence includes controlled permission checks, small real CPU inference checks, and Laya comparisons against provisional labels. These are distinct forms of evidence; provisional-label agreement is not independent human-ground-truth accuracy. Fine-tuning, calibration, and checkpoint promotion remain future work.

## Demonstration

The plugin is under separate development in `plugin/`. The research repository includes a [local simulated demonstration](docs/guides/reproduce.md); it does not connect to real email, banking, or file-changing services.

## License and acknowledgment

This repository is released under the [Apache License 2.0](LICENSE). Model checkpoints, AgentDojo, datasets, and external assets retain their own licenses and terms.

Developed with Graduates Rising in Data Science at USC.

## Authors

<p>
  <a href="https://github.com/Siddharth-magesh"><img src="https://images.weserv.nl/?url=github.com%2FSiddharth-magesh.png&amp;w=100&amp;h=100&amp;fit=cover&amp;mask=circle" width="100" height="100" alt="Siddharth Magesh" /></a>
  <a href="https://github.com/AtharvaThorat"><img src="https://images.weserv.nl/?url=github.com%2FAtharvaThorat.png&amp;w=100&amp;h=100&amp;fit=cover&amp;mask=circle" width="100" height="100" alt="Atharva Thorat" /></a>
  <a href="https://github.com/kaustubhadhe1206"><img src="https://images.weserv.nl/?url=github.com%2Fkaustubhadhe1206.png&amp;w=100&amp;h=100&amp;fit=cover&amp;mask=circle" width="100" height="100" alt="Kaustubh Adhe" /></a>
</p>

[Siddharth Magesh](https://github.com/Siddharth-magesh) Â· [Atharva Thorat](https://github.com/AtharvaThorat) Â· [Kaustubh Adhe](https://github.com/kaustubhadhe1206)

<p align="right"><a href="#permissions-that-learn">Back to top</a></p>
