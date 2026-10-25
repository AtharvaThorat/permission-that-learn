## Person 1 — Freeze and Validate the Runtime Environment

Own the reproducible execution environment and configuration. Select exactly one acting model for the smoke test, preferably the model already supported by the team setup. Record its model ID, checkpoint or served-model name, endpoint URL, inference parameters, tokenizer/template settings, Python version, AgentDojo revision, Laya version/checkpoint, wall configuration, gatekeeper configuration, and required environment variables. Confirm that the model endpoint is reachable and that the required AgentDojo, Laya, wall, PyTorch, and tokenizer dependencies are installed in the intended environment. Do not run the full benchmark or multiple models.

Prepare one small clean email/calendar task and define the exact task input, expected tool calls, environment metadata, and reset procedure. Create three explicit configurations using the same actor and task: `unprotected`, `wall_only`, and `wall_gatekeeper`. Ensure each run starts from an independently reset AgentDojo environment. Confirm that credentials are supplied through environment variables and are never written into configuration files or logs. Document the exact command that another person can use to reproduce the environment and run the selected task. Before handing off, provide a short environment manifest containing model identity, dependency versions, task ID, mode configuration, endpoint information, resource assignment, and known limitations. Do not declare success merely because imports work; verify that the selected model can produce at least one valid tool-capable response.

**Deliverables:**

- Frozen smoke-test configuration.
- Environment/dependency manifest.
- Selected clean task and reset instructions.
- Credential and endpoint setup instructions.
- One validated model request/response test.
- Exact commands for running each of the three modes.

---

## Person 2 — Verify Runtime Protection, Wall, Gatekeeper, and Artifact Handling

Own the code-path and observability verification. Review the existing shared runtime, AgentDojo integration, `PtlWall` adapter, gatekeeper adapter, result storage, and experiment CLI before executing the real smoke test. Confirm that all three modes use the same actor and task setup but route actions differently:

- `unprotected`: the proposed action reaches the simulated executor without the permission layer.
- `wall_only`: the action is evaluated by the real wall before execution.
- `wall_gatekeeper`: the action passes through the real wall and then the Laya gatekeeper when required.

Add or verify temporary instrumentation only if the existing trace output is insufficient. Do not redesign the runtime or create a second execution path. Confirm that every actor proposal, normalized action, wall verdict, gatekeeper recommendation, final decision, tool dispatch, tool result, error, timing, token count, and lifecycle status is persisted. Ensure protected modes cannot silently fall back to `unprotected` if the wall or gatekeeper is unavailable. Missing dependencies, malformed decisions, timeouts, or gatekeeper errors must produce explicit failures or unresolved/pending states.

Use controlled cases to validate behavior before or alongside the real task:

1. An allowed action that should execute.
2. A prohibited action that the wall should block.
3. An action requiring confirmation that should remain pending until an explicit approval or rejection is supplied.
4. A stale or mismatched permission evidence case that must not execute.
5. A gatekeeper failure or timeout that must not become automatic approval.

Verify that the output handler creates separate artifacts for each mode and attempt, including JSON and CSV results. Confirm that retries do not overwrite earlier attempts and that missing metrics remain null or explicitly missing. Verify that source artifacts remain unchanged if replay is used. Do not alter policy semantics merely to make the smoke test pass.

**Deliverables:**

- Runtime-path verification checklist.
- Evidence that each mode used the intended protection path.
- Sample traces for allow, block, and pending-approval behavior.
- Confirmation that blocked tools were not dispatched.
- Confirmation that protected-mode failures do not fall back to unprotected execution.
- Example JSON/CSV result artifacts and their locations.
- List of any concrete code or configuration defects found.

---

## Person 3 — Execute the Smoke Test and Produce the Comparison Report

Own the actual controlled execution and result analysis, after Persons 1 and 2 provide their deliverables. Do not expand the scope beyond one acting model and one selected clean email/calendar task. For each mode, reset the environment independently and run the exact same task:

1. `unprotected`
2. `wall_only`
3. `wall_gatekeeper`

Run them sequentially first, even if the final platform will support parallel execution. Record the run ID, job ID, attempt ID, model identity, mode, task identity, seed, environment reset state, start/end times, actor calls, token usage, wall calls, gatekeeper calls, tool proposals, actual tool dispatches, denials, approvals, errors, latency, and final task outcome.

For each execution, inspect both the terminal output and persisted artifacts. Confirm that the unprotected run is genuinely unprotected, that `wall_only` records real wall evidence, and that `wall_gatekeeper` records both wall and gatekeeper decisions. Compare proposed actions with executed actions. Pay particular attention to actions that are denied or require approval: a blocked action must not appear in the tool execution trace, and an approval-required action must remain pending unless a deliberate approval is provided. Check that the run reports distinguish successful completion, pending approval, failure, interruption, and missing metrics.

Generate a concise comparison table with at least:

- Mode.
- Task ID.
- Run/attempt ID.
- Task completion status.
- Attack status, if applicable.
- Proposed action count.
- Executed action count.
- Wall verdicts.
- Gatekeeper decisions.
- Blocked action count.
- Pending approval count.
- Actor calls and tokens.
- Gatekeeper calls and tokens.
- Total duration.
- Errors or unresolved decisions.
- Artifact directory.

Do not summarize the result as “protection worked” merely because fewer actions executed. Explain whether the task completed, whether the action was appropriate, whether a failure came from the model, wall, gatekeeper, environment, or missing approval, and whether the result is comparable across modes. Preserve all raw artifacts and do not overwrite failed attempts.

If the smoke test fails, classify the failure before requesting changes:

- Environment/dependency failure.
- Model endpoint or actor failure.
- AgentDojo task/runtime failure.
- Wall integration failure.
- Gatekeeper/Laya failure.
- Artifact/output failure.
- Incorrect fallback or authorization behavior.

Then send the precise failure evidence to the responsible person. Do not broaden the experiment or modify unrelated modules. After a successful smoke test, freeze the resulting configuration and recommend the next step: a small paired clean/attacked demonstration using approximately five tasks, rather than a large multi-model benchmark.

**Deliverables:**

- Three completed smoke-test runs.
- Raw JSON/JSONL/CSV artifacts for every run.
- A mode comparison table.
- One or more representative traces.
- A failure/limitation log.
- Confirmation that no tools executed when denied.
- Confirmation that approval-required actions remained pending without approval.
- Recommendation## Person 1 — Environment, Model, and Dependency Freeze

Prepare and freeze the complete runtime environment before anyone runs the smoke test. Select one tool-capable acting model already supported by the team, preferably the existing Qwen/OpenAI-compatible setup. Record the exact model ID, checkpoint or served-model name, revision, tokenizer/template configuration, inference parameters, endpoint URL, Python version, CUDA/GPU information, AgentDojo revision, Laya version/checkpoint, wall version, and all dependency versions. Confirm that credentials are supplied only through environment variables and are never written into tracked files or result artifacts. Verify that the actor endpoint responds to a minimal health or model-metadata request without executing an AgentDojo task. Confirm that the selected AgentDojo email/calendar task and its required tools are available. Prepare a fresh, isolated runtime/environment reset procedure so that each mode starts from identical initial state. Do not run the full experiment or multiple models. Deliver a frozen configuration file, an environment/version manifest, a list of required environment variables, the exact task ID, and the exact command that Person 2 and Person 3 should use. If any dependency, model endpoint, Laya asset, or AgentDojo compatibility issue prevents execution, document the precise failure and stop there rather than substituting an unverified fallback.

## Person 2 — Unprotected Baseline Execution

Using only Person 1’s frozen configuration and a freshly reset AgentDojo environment, execute the selected clean email/calendar task in `unprotected` mode. This run establishes the baseline against which both protected modes will be compared. Do not change the acting-model settings, task input, task state, tool inventory, seed, timeout, or environment initialization. Capture the complete run directory, including the experiment specification, resolved configuration, actor requests and responses, proposed tool calls, normalized actions, tool arguments, tool results, dispatch counts, task completion status, timing, token/call usage, errors, and any AgentDojo-native scoring output. Verify that the run actually used the unprotected path and did not invoke the wall or gatekeeper. Confirm whether each proposed action was executed and whether the task completed successfully. Preserve all raw artifacts; do not summarize over or delete them. After execution, produce a short baseline report containing the run ID, task ID, model identity, mode, actions proposed, actions executed, final task outcome, latency, token/call counts, and any failures. Person 2 should not modify the runtime implementation unless there is a clear execution defect; report defects with logs and exact reproduction commands so they can be fixed separately.

## Person 3 — Protected Wall and Gatekeeper Verification

Using the same frozen configuration, same task, same seed, and separately reset environments, run the task first in `wall_only` mode and then in `wall_gatekeeper` mode. These must be two independent runs, not a continuation of the unprotected run. Verify that `wall_only` uses the real `PtlWall` adapter and records the wall verdict for every proposed action. Verify that prohibited actions are blocked before tool execution, permitted actions execute only after the wall allows them, and unresolved or approval-required actions remain visibly pending rather than being silently approved. Then verify that `wall_gatekeeper` invokes both the real wall and the Laya gatekeeper path. Capture the raw wall evidence, policy/state versions, gatekeeper request, raw recommendation, final decision, approval state, tool dispatches, tool results, task outcome, latency, token/call usage, and all errors. Specifically test or identify at least one allowed action, one blocked action, and one action that requires confirmation; if the selected task does not naturally produce all three cases, use the smallest approved fixture or controlled action case without changing the main task’s semantics. Confirm that no protected run silently falls back to `unprotected`, that blocked actions never reach the executor, and that source artifacts are preserved. Produce a protected-mode report comparing `wall_only` and `wall_gatekeeper` against Person 2’s baseline, including mode identity, wall/gatekeeper decisions, executed versus blocked actions, pending approvals, and any truncation or runtime failures.

## Coordination and Handoff Order

1. **Person 1 must finish first** and publish the frozen configuration, environment manifest, task ID, reset procedure, and commands.
2. **Person 2 runs the unprotected baseline** and publishes the complete raw run artifacts plus baseline summary.
3. **Person 3 runs both protected modes** using the exact same frozen inputs and separate resets.
4. All three people compare only matching identities:
   - same task
   - same seed
   - same model
   - same AgentDojo version
   - same input
   - same initial environment
   - different mode only
5. The final smoke-test package should contain:
   - `environment-manifest.json`
   - frozen experiment configuration
   - one unprotected run
   - one wall-only run
   - one wall-gatekeeper run
   - raw traces for actor, wall, gatekeeper, tools, and errors
   - JSON and CSV summaries
   - a comparison table
   - a short failure/limitation report
6. Do not proceed to multiple models, broad parallelism, approval memory, Jev, or the larger clean/attacked benchmark until all three modes are shown to execute correctly and the artifacts demonstrate that protection is actually enforced.