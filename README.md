# Permissions That Learn: Laya gatekeeper

This local component validates one proposed action, consumes a **mocked wall** verdict,
asks Laya about task authorization, and applies deterministic enforcement rules.
`ALLOW`, `ASK`, and `BLOCK` are decisions only: no email, calendar, or file tool executes.
The current argmax policy is an **experimental baseline, not a validated
automatic-authorization policy**.

The [contract](data/gatekeeper_contract.md) and 20 synthetic development fixtures are
unchanged from the prototype. The wall, authentic request, and verified context must
come from a trusted harness. Matching action IDs alone is insufficient for production
execution binding; production would need canonical action binding, current-policy
revalidation, approval expiry, and execution-side checks. No wall implementation,
AgentDojo, approval memory, Jev adapter, or cascade is included. Email validation and
the exact English UTC time recognizer remain deliberately narrow.

## Setup and offline checks (Windows PowerShell)

Run from the repository root. The verified interpreter is **Python 3.13.9**, not
Python 3.11. For this two-workspace layout, a fresh isolated environment can use the
existing prototype interpreter as its bootstrap without modifying that environment:

```powershell
$Python = (Resolve-Path '..\codespace\.venv\Scripts\python.exe').Path
& $Python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m gatekeeper examples\read-file.json
```

On another machine, set `$Python` to an installed Python 3.13.9 interpreter instead.
Do not use `--system-site-packages`. The source prototype inherited Miniconda packages
(including Pydantic); the tested destination environment has
`include-system-site-packages = false`. `requirements.txt` pins the existing core
inference stack; `requirements-lock.txt` records the tested full destination stack.
The tested Torch wheel is CPU-only. No working core package was upgraded.

For a lighter test-only environment, install `requirements-test.txt` instead. Package
installation requires an index or local wheels; **running the tests requires neither
network nor Laya/weights**. Tests use explicit mocks, fake spawned workers, and saved
response replay. They do not download models. There was no existing CI configuration.
The offline CLI deliberately returns `ASK / MODEL_UNAVAILABLE`, marked `offline-demo`.

## Request, output, and importable API

[examples/read-file.json](examples/read-file.json) is a complete valid request:

```json
{
  "schema_version": "0.1", "request_id": "demo-request", "task_id": "demo-task",
  "user_request": "Read file notes-7.",
  "action": {"action_id": "demo-action", "tool": "files.read", "arguments": {"file_id": "notes-7"}},
  "wall": {"verdict": "PASS", "policy_version": "mock-demo-v1", "evaluated_action_id": "demo-action", "reason_codes": []},
  "verified_context": {"confirmation_required": false, "evidence_complete": true, "facts": {"accessible_file_ids": ["notes-7"]}}
}
```

The real baseline smoke request produced this decision object (not an execution):

```json
{"request_id": "demo-request", "action_id": "demo-action", "decision": "ALLOW", "reason_code": "TASK_AUTHORIZED"}
```

Use a guarded entry point for Windows multiprocessing. The example below uses real
inference and may download weights:

```python
import json
from pathlib import Path
from gatekeeper import Gatekeeper, GateDecision, LayaBackend

def main():
    request = json.loads(Path("examples/read-file.json").read_text())
    with Gatekeeper(LayaBackend(cache_dir=".cache/huggingface")) as gate:
        gate.initialize()  # Explicit load + unchanged notes-7 warm-up; optional.
        result: GateDecision = gate.evaluate(request)
        print(result.output.model_dump())
        print(result.class_probabilities, result.error_kind)

if __name__ == "__main__":
    main()
```

`evaluate` accepts a request dictionary or `Request`. It validates arguments and wall
binding before lazy model initialization. Reuse the same gate/backend across requests.
`initialize()` loads once and warms up; inspect `backend.error` and `backend.metadata`.
Context exit or `close()` shuts down the worker; closing is idempotent and terminal.
Create a new backend to retry a failed initialization or timeout. Calls on one backend
are serialized. There is no automatic checkpoint/device substitution.

## Explicit real-model verification

```powershell
.\.venv\Scripts\python.exe -m gatekeeper examples\read-file.json --real-model
.\.venv\Scripts\python.exe -m scripts.evaluate --question-mode single --checkpoint-profile baseline --output-dir results\local-single-01
.\.venv\Scripts\python.exe -m scripts.verify_baseline results\local-single-01
```

Choose a new output directory on repeat evaluation; existing results are never
overwritten. The evaluator also defaults to a unique directory if `--output-dir` is
omitted. Real CLI/evaluation exits 2 on model failure, 0 on completed evaluation
(including incorrect decisions). Unit tests and live inference remain separate.

First inference needs Hugging Face access and enough disk/memory for the Laya checkpoint
and its ModernBERT encoder/tokenizer dependencies. Downloads can take longer than warm
inference. No paid service is used. Cache defaults to `.cache/huggingface`, configurable
with `--cache-dir`, the Python `cache_dir` argument, or `LAYA_CACHE_DIR`. No credentials
or environment template are needed for these public checkpoints.

To reuse the prototype cache without a network request, as in the migration verification:

```powershell
$env:HF_HUB_OFFLINE = '1'
try {
  .\.venv\Scripts\python.exe -m scripts.evaluate --cache-dir ..\codespace\.cache\huggingface --output-dir results\cached-single-01
  .\.venv\Scripts\python.exe -m scripts.verify_baseline results\cached-single-01
} finally {
  Remove-Item Env:HF_HUB_OFFLINE
}
```

If any required cache artifact is missing, offline inference fails conservatively.
For normal download mode leave `HF_HUB_OFFLINE` unset. Both CLI and evaluator expose
`--load-timeout 300` and `--timeout 60` (seconds). The same options are `load_timeout`
and `timeout` on `LayaBackend`. Initialization/download/load time, first warm-up time,
and subsequent inference/IPC times are recorded separately.

## Model selection and experimental options

[gatekeeper/model_manifest.json](gatekeeper/model_manifest.json) owns the explicit pins:

| Profile | Checkpoint | Revision |
|---|---|---|
| baseline (default) | `convaiinnovations/laya` | `7b928d828b7b0e022f929d9bd2e44165aa270148` |
| typed-decisions (experimental) | `convaiinnovations/laya-typed-decisions` | `e929ae5cf69bc34259cd2f95c9e91145b818b1f0` |

The baseline pin was recovered from the prototype's `experiment.json`. CPU eager
inference and `single-v1` are defaults. Loaded identity, revision, device, native
configuration, and temperature warnings are recorded and checked. Encoder dependencies
follow the checkpoint's native configuration; the manifest does not independently pin
every upstream encoder repository. No calibration, thresholds, or prompt tuning was added.

```powershell
.\.venv\Scripts\python.exe -m scripts.evaluate --question-mode decomposed
.\.venv\Scripts\python.exe -m scripts.evaluate --checkpoint-profile typed-decisions
```

`decomposed-v1` asks two questions in one call, combines their categorical answers in
code, and preserves each probability distribution separately. For explicit repository
selection, evaluator `--checkpoint <repository> --revision <40-character-commit>` and
`LayaBackend(checkpoint=..., revision=...)` are available. Unknown repositories require
their own revision. Registered repositories always resolve their own pin.

## Enforcement, diagnostics, and modules

Order remains: invalid request/action/binding; wall DENY or missing/UNKNOWN; known
task contradiction (including the narrow exact-time check); mandatory confirmation;
incomplete evidence; semantic decision/fallback. A contradiction precedes confirmation.
Model failure never grants ALLOW, and confirmation/evidence overrides still apply.

`GateDecision.output` is the final policy decision. `raw_model_output`,
`raw_model_decision`, `class_probabilities`, `raw_answers`, and
`probabilities_by_question` preserve the model evidence separately. Provider confidence
is not a replacement for class probability. `combined_semantic_decision` is before
policy overrides; in decomposed mode it is computed, not a model-returned decision.

Errors distinguish `download_or_load_failure`, `initialization_timeout`,
`inference_failure`, `inference_timeout`, `invalid_response`, `truncation`, and `closed`.
The underlying exception text is retained. Missing/invalid labels, distributions,
and required truncation diagnostics are rejected. This intentionally tightens malformed
response handling from the prototype without changing valid-output decisions.

| Module | Responsibility |
|---|---|
| `gatekeeper/schemas.py`, `validation.py` | Strict request/output schemas, tool arguments, action-ID binding, exact time check |
| `gatekeeper/state.py`, `questions.py` | Allowlisted request/context serialization and versioned unchanged templates |
| `gatekeeper/config.py`, `model_manifest.json` | Explicit model selection and independent revision pins |
| `gatekeeper/laya_adapter.py` | Persistent spawned CPU worker, response validation, timing, lifecycle and failures |
| `gatekeeper/policy.py` | `Gatekeeper.evaluate(request) -> GateDecision`, deterministic enforcement |
| `gatekeeper/__main__.py` | Local offline/explicit-real CLI; no tool execution |
| `scripts/evaluate.py`, `compare*.py`, `verify_baseline.py` | Offline fixture evaluation, experiment reporting, reproduction checks |

Only authentic request text, proposed tool/arguments, and verified context enter model
state. Fixture labels, titles, rationales, categories, and IDs stay outside it. Callers
must keep evaluator metadata out of the harness's context facts. Reports contain full
inputs and raw diagnostics and are ignored under `results/`.

## Preserved development observations

Verified against completed source reports, not the stale source README:

| Configuration | Final accuracy | Raw/combined semantic accuracy | Incorrect ALLOWs |
|---|---:|---:|---:|
| Original, single | 14/20 | 7/15 | 5 |
| Original, decomposed | 14/20 | 7/15 | 6 |
| Typed-decisions, single | 13/20 | 6/15 | 7 |

These are observations on 20 known development examples, not general safety results.
Semantic accuracy compares pre-override output to final fixture labels on 15 called
cases; five deterministic cases bypass inference. Equal accuracy can hide an increase
in incorrect ALLOWs. The [compact snapshot](benchmarks/development/observations.json)
records source report paths, hashes, native configuration, and dependencies; saved single
responses support regression replay. Full historical runs remain in the source workspace.

Migration verification on Windows/Python 3.13.9: **45 tests and 62 subtests passed**,
`pip check` passed, and a real single-question CPU run reproduced all 20 final outputs,
raw decisions, and model-state hashes with matching core dependencies and configuration.
No behavior differences were observed on the baseline fixtures. See
[verification.json](benchmarks/development/verification.json) for compact measured evidence.
