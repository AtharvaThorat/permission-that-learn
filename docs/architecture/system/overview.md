# System architecture

`grids` is installed from `src/grids` and exposed through one CLI (`python -m grids`).
Use an editable source checkout: command profiles and examples live in `configs/`.

| Package | Responsibility |
|---|---|
| `actors` | OpenAI-compatible client, profile validation, vLLM serving |
| `benchmarks/agentdojo` | Native suite schemas, context facts, codec, attacks, pipeline interception |
| `core` | Action binding, controller, dispatch ledger, approval providers, audit |
| `wall` | Deterministic capability/resource/recipient policy and verified identity context |
| `gatekeeper` | Pinned Laya worker, context preparation, prediction and conservative decision mapping |
| `runs` | Deterministic plans, bounded scheduling, model services, attempts, native scoring and live reports |
| `evaluation` | Frozen datasets, independent labels, offline comparators and authorization metrics |
| `cli` | Setup, serving/validation, live runs, capture/evaluation and reports |

Live flow: native task initialization → actor → exact call parsing → action binding
→ Wall → Laya when configured → approval/enforcement → native tool dispatch → actor
continuation → native scoring → persisted attempt. Each episode has fresh state.

Workspace, Slack, and Banking use suite-aware fact resolution but the same controller.
Trusted identities are taken from the clean task-initialized environment; retrieved
messages and injection content are not user authorization. Missing metadata is explicit.

The proposal batch is recorded before parsing. Each parsed action also records the
current pre-action environment, including changes from earlier actions in the same
batch. Capture preserves cancelled and invalid proposals; it does not fabricate actions.
Permission context includes native revision, schemas, policy, identities, and metadata.
Native evaluation goals/scores are stored separately and excluded from replay inputs.

AgentDojo is pinned to `089ed468cf3ed0322acc66b0211f26d9d90dbf60` (`0.1.35`, suite
version `v1.2.2`). Its native `run_task_with_pipeline` computes task/security outcomes.
No local clone or version upgrade is part of this refactor. See the
[upstream source](https://github.com/ethz-spylab/agentdojo/tree/089ed468cf3ed0322acc66b0211f26d9d90dbf60).
