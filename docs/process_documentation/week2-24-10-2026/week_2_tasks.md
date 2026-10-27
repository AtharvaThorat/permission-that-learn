# Week 2 — Real AgentDojo Evaluation and Prototype Completion

These assignments are based on the supplied `project_tracking.md`, including its October 24 update. They carry forward unfinished Week 1 execution work and define the work needed for the October 31 prototype demonstration. The tracker records a real panel-15 unprotected run, but the corresponding protected panels have not been completed. The HARD-panel run failed validation, and the recorded protected single-task run did not produce a real Laya decision because the model failed to load. These assignments therefore prioritize a trustworthy three-mode comparison before adding new models or features. Repository and raw-run details must be verified by the assigned owners; the tracker alone is not independent validation of the artifacts.

The required Week 2 evaluation is the existing panel-15 with `Qwen/Qwen2.5-7B-Instruct`, using the same verified 4-bit serving setup across `unprotected`, `wall_only`, and `wall_gatekeeper`. Fifteen cases, each evaluated in clean and attacked conditions across three modes, produce a planned matrix of 90 episodes. This completes the selected project panel, not the entire AgentDojo benchmark. The existing 30-episode unprotected run can contribute to this matrix only if its artifacts pass validation and match the frozen setup. Otherwise, it must be rerun. Keep the tracker’s one-GPU-at-a-time constraint and proposed 30 GPU-hour ceiling, and estimate the remaining cost from actual pilot execution before scheduling the full matrix.

## Expanded assignment update (2026-10-27)

The owner subsequently requested three suites and two actors. See the
[six-task implementation and evidence record](SIDDHARTH_TASK1_COMPLETION.md#october-27-six-task-extension).
292 CPU tests passed (one skipped); 37 real native attempts were saved and
verified. The Qwen2.5 Slack attack succeeded in every mode, including Laya;
Workspace ASK remains pending. This is functional readiness, not validated
security effectiveness or completion of the original panel-15. CARC smoke
verification, policy review and teammate acceptance remain open.

## Task 1 functional validation update (2026-10-25)

Owner-requested scope: small functional checks and one optional actor; no panel,
sweep or quality comparison. Branch: `fix/real-pipeline-functional-validation`.

- Fixed local Laya revision reporting after verifying the actual nested tokenizer
  layout. Added explicit bounded context override; preserved fail-closed truncation
  and recorded initialization/raw inference errors.
- Real standard T4: baseline Qwen2.5 ran `user_task_0` in three fresh modes; native
  utility False in unprotected/wall-only reflects its wrong-year search. Default
  gatekeeper input truncated; the explicit 8192 rerun produced genuine ASK without
  dropping evidence. Laya stayed on CPU.
- Optional Qwen3-4B loaded, passed tool parsing, and produced genuine protected
  ASK on `user_task_1`. `user_task_10` additionally proved real Laya ALLOW, native
  date dispatch, actor continuation, then pending ASK. No protected task completed.
- Worker/publication errors and pending approvals are durable; HTML reports show
  every attempt, chronological decisions and raw links. Native-score failures keep
  metrics missing. Full CPU regression: **259 passed, 1 skipped**; controlled
  enforcement: **12/12**. These controlled cases are separate from real inference.
- Evidence: `results/functional-20261025/` (six verified episode checksums), plus
  `results/functional-controlled-20261025/`. T4 shutdown confirmed; no assignments
  remain. [Handoff](../../../SETUP_HANDOFF.md#functional-validation-2026-10-25)
  gives versions, exact commands, run IDs, viewer paths and limitations.
- Remaining: review/PR, Laya calibration and legitimate-task utility, then the
  separately approved matched panel. Existing frozen profiles were not modified;
  longer-context compatibility does not solve arbitrary truncation or establish
  attack resistance. No reusable approval memory was introduced.

## Task 1 closeout assessment and CARC preparation (2026-10-26)

**Status: core implementation verified; full handoff/freeze not yet complete.**

The [Siddharth Task 1 completion note](SIDDHARTH_TASK1_COMPLETION.md) records the
completed implementation and evidence. Siddharth plans to verify CARC later;
team agreement on benchmark settings and approval policy is also still open.

| Requirement | Evidence / remaining work |
|---|---|
| Real pinned assets and inference | Verified on Colab T4 with CPU Laya; actual nested tokenizer assets and revision-reporting fix. |
| Decisions through enforcement | Real ALLOW dispatched a native tool; real ASK prevented dispatch. Denied violations, unavailable/malformed models and stale/changed approval bindings are separately CPU/controlled-tested. |
| Context preservation | Real multi-turn continuation and 4007-token full evidence verified with explicit override; over-limit evidence fails closed. This is not a general truncation or utility solution. |
| Reproducible handoff | Commands, profiles and raw evidence exist; teammate reproduction/receipt of the ignored artifact bundle has not been confirmed. |
| Freeze and unattended approvals | Pending remains terminal; agreement with Atharva and a versioned benchmark freeze are still required. Existing frozen configs remain unchanged. |
| CARC execution | Not run. Linux job environment reported, but cluster/scheduler/account/partition/storage details remain unknown. |

Added `scripts/machine_setup.py` for selected/all environment installation,
pinned downloads and validated experiment config generation. Execution, model
phase selection, concurrency, resume and reports reuse the existing experiment
CLI; server switching/allocation stays explicit. The
[user manual](../../user_manual/MACHINE_SETUP_AND_RUNS.md) provides commands and
a conditional Slurm template. Six new offline tests passed; full regression:
**265 passed, 1 skipped**. No CARC access, installation, model inference, or panel
run was performed in this follow-up. Branch: `feat/machine-setup-cli`, based on
the verified functional commit `f5c038a`; owner push/PR is required for remote use.

## Documentation maintenance (2026-10-24)

Completed: contributor rules and project/directory READMEs refreshed; weekly
process links checked. Remaining: user review and PR merge. This documentation
work does not complete the runtime or evaluation tasks below. See the
[project tracker](../../project_tracking.md) for overall progress and follow the
[project guidelines](../../PROJECT_GUIDELINES.md) for every task.

## Task 1 — Siddharth Magesh: Complete Real Laya Integration and Freeze the Gatekeeper

Your responsibility is to make the integrated `wall_gatekeeper` mode use the actual Laya model reliably and provide a reproducible handoff for the protected benchmark. This task carries forward Week 1’s unfinished checkpoint-loading verification, real inference validation, realistic context handling, and pending-approval verification. For coding instructions, repository conventions, implementation requirements, and testing expectations, read `docs\PROJECT_GUIDELINES.md` before making changes. Inspect the current implementation and reuse the existing adapter, controller, input preparation, and tests rather than rebuilding the permission pipeline.

**Reconcile the existing fixes and establish the real runtime.** Start by inspecting the current Laya adapter, configuration, checkpoint resolution, initialization, and error reporting. The tracker says D8, involving the checkpoint’s `tokenizer/` layout, and D9, involving missing initialization error details, have already been fixed on `main`. Confirm that the fixes are present and then exercise them with the actual pinned assets. Distinguish code that exists, code covered by CPU tests, and behavior verified through real inference. If another initialization problem appears, preserve the actual error, the environment, and the reproduction conditions instead of treating every failure as a generic unavailable-model outcome.

Validate the pinned local checkpoint, tokenizer, encoder, processor, and other required assets in the intended execution environment. Record the repository and exact revision, resolved snapshot, relevant package versions, device, numerical precision, supported context limit, and initialization duration. Follow the project’s split model/runner environment arrangement where required and describe how those environments communicate. Keep Laya on CPU where supported. If the existing arrangement is infeasible, document the measured compatibility or performance problem and coordinate any resource change before the benchmark is frozen. A snapshot that exists on disk, a successful import, or a mocked response is not sufficient evidence: the handoff must include successful loading followed by an actual inference response.

**Verify real decisions through enforcement.** Use a small development set to demonstrate that actual Laya output is parsed and reaches the controller correctly. Include a legitimate action that can proceed, an ambiguous request that should remain pending for confirmation, and a policy violation that must not execute. Also validate handling of model unavailability, malformed responses, stale permission evidence, and evidence that no longer matches the proposed action. Failure-handling checks may use controlled faults, but label those separately from real semantic inference. Do not report a wall denial as a correct Laya classification if the wall prevented the model from being called.

For each development case, preserve the proposed action and relevant task context, the wall outcome, whether Laya was invoked, the model response when available, the parsed decision, the final enforcement outcome, and whether tool dispatch occurred. Distinguish a genuine semantic ASK from an operational error converted into an ASK-shaped fail-closed outcome. The previous `MODEL_UNAVAILABLE` results are gatekeeper failures, not evidence of successful judgment. If real Laya decisions are incorrect or inconsistent, retain those findings and explain them; the objective is a valid baseline rather than a hand-picked set of apparently perfect outcomes.

**Verify input preparation on realistic multi-turn context.** Exercise the gatekeeper with representative AgentDojo development trajectories, including longer tool outputs. Check that the existing character budget and summarization safeguards preserve user intent, task boundaries, tool arguments, recipient and resource identity, relevant policy, evidence freshness, and the distinction between trusted instructions and untrusted tool content. Measure token usage using the actual tokenizer where supported, because a character limit alone does not establish that the model context window is respected. Record when truncation or summarization occurs and whether decision-critical information is lost. Missing permission evidence must not silently become authorization.

Any input-preparation or configuration adjustments should be developed on clearly identified development cases and frozen before the formal panel runs. Preserve the original configuration and describe the change and its reason. Do not repeatedly tune the gatekeeper against final panel outcomes and then present those same outcomes as an untouched evaluation. If a necessary fix changes behavior after benchmarking starts, coordinate a new configuration version and identify which runs need to be repeated.

**Confirm pending approval semantics without expanding into approval memory.** Verify that a genuine ASK prevents dispatch while approval is pending, remains bound to the action and evidence that were reviewed, and cannot authorize changed arguments, recipients, resources, or stale policy context accidentally. Agree with Atharva on one explicit unattended-benchmark policy before execution. Pending outcomes should remain visible; do not automatically approve all requests merely to improve task completion. An interactive demonstration can separately show a human granting or rejecting approval, provided the intervention is recorded and kept distinct from unattended benchmark results.

Reusable approval memory is outside the required Week 2 baseline. The existing action-bound approval mechanism must not be described as reusable memory. Jev integration, weight fine-tuning, and broad model changes are also deferred until the current pipeline has a validated real comparison. If an existing enforcement defect blocks correct operation, fix that defect within the current scope and provide focused evidence under the repository guidelines.

**Deliver the gatekeeper handoff and support execution.** Give Atharva the verified prerequisite information, runtime provenance, real inference proof, representative integrated traces, frozen gatekeeper settings, context-handling limits, and known failure conditions. The handoff must let another person reproduce the real decision path without relying on notebook state that exists only in your session. During the protected panel runs, support diagnosis of loading, inference, parsing, and context failures, but avoid unrecorded changes to the frozen configuration.

Task 1 is complete when another teammate can reproduce an actual Laya-backed decision through the integrated runtime, enforcement behaves correctly for the reviewed cases, and operational failures are clearly separated from semantic decisions. Update the tracker with the actual evidence and remaining limitations. Passing CPU tests alone, resolving a snapshot path, or producing only `MODEL_UNAVAILABLE` outcomes does not complete this task.

## Task 2 — Kaustubh Adhe: Validate the Unprotected Baseline and Freeze the Evaluation Panel

Your responsibility is to establish a trustworthy unprotected baseline and own the common task and attack specification used by all three configurations. This task carries forward Week 1’s inaccessible raw baseline evidence, incomplete attack exposure, `user_task_7` failures, and failed HARD-panel reporting. For coding instructions, repository conventions, implementation requirements, and testing expectations, read `docs\PROJECT_GUIDELINES.md` before making changes. Reuse the existing baseline notebook, run validator, reporting scripts, and panel configurations wherever they already satisfy the requirements.

**Retrieve and audit the real panel-15 artifacts.** Begin with `panel-15-unprotected-df0505e87cf64624`. The tracker says its raw artifacts are on the owner’s Drive rather than in the repository. Place the required evidence in the project’s agreed artifact location and provide a usable reference so Atharva can validate and compare it independently. Preserve configuration files, raw episode records, attempt histories, scoring outputs, and available traces rather than sharing only a workbook or screenshot. Sanitize credentials and secrets without removing the provenance needed to reproduce the experiment.

Audit all 30 planned episodes and their pair identities, attempts, terminal states, checksums, source and configuration revisions, actual model revision, quantization, serving parameters, prompt version, generation settings, reset evidence, attack identities, native evaluator results, and exposure records. Historical execution settings must be established from the run evidence, not inferred from a configuration file that may have changed since execution. The tracker reports clean utility of 6/15, injection exposure in 7/15 attacked episodes, and attack success of 0/7 among exposed episodes. Reproduce those numbers from the raw artifacts and state any qualification imposed by validation or missing scoring.

**Diagnose baseline failures and resolve panel validity.** Review unsuccessful clean and attacked episodes and distinguish actor mistakes, wrong-year searches, invalid tool arguments, invented identifiers, server timeouts, model request failures, uncertain tool execution, scoring failures, and incomplete artifacts. Investigate `user_task_7`, which reportedly ended as `infrastructure_error` in both conditions after an invented event ID. Determine whether this classification matches the existing execution semantics. Do not broadly reclassify errors or suppress failed runs to make the baseline appear healthier. Any correction should be justified by the actual tool behavior and the repository’s documented contracts.

Keep all 15 cases, including `user_task_7`, by default. Poor actor performance is not a reason to remove a case. If a genuine benchmark or integration defect makes a case invalid, record the evidence and apply the same predeclared exclusion across all three modes. If the panel is reduced, update the planned episode count and explain the change. Preserve the original results so the final report does not hide how the evaluation scope changed.

**Audit attack placement and exposure.** For every attacked case, document the legitimate user task, attacker objective, exact payload, injection location, why that location is relevant, and whether the actual actor trajectory encountered it. Distinguish a planned attack from a successfully inserted payload, a payload returned by a tool, and a payload actually included in actor-visible context. Verify how the existing tooling measures exposure and how attacker success is scored. A reference solution reading the injection location does not guarantee that the tested actor will do so.

The recorded 7/15 exposure rate limits what can be concluded from the existing attack results. Do not describe 0/7 exposed successes as resistance to all 15 attacks. Record non-exposure separately from unsuccessful attacks, missing scores, and infrastructure failures. If payload placement must change, version the attack panel and rerun the corresponding baseline rather than silently mixing old and new attack conditions. Avoid optimizing the attack panel solely around the actor’s observed final-evaluation trajectory without disclosing that development process.

**Freeze the shared evaluation specification.** Provide one authoritative manifest covering the exact task and attack identities, clean/attacked pairing, model checkpoint and serving provenance, quantization, system prompt version, seed, generation settings, episode limits, timeout policy, retry policy, attempt-selection policy, environment reset procedure, exposure definition, native scoring behavior, and any exclusions. Coordinate with Siddharth on the frozen gatekeeper version and with Atharva on approval handling and protected configuration comparability. The only intended differences across modes should be the declared protection configuration and its resulting behavior.

Verify that the three panel configurations still produce matching pair identities in the actual runtime. The tracker records a historical path requirement involving `/content/permission-that-learn`; follow the documented setup where necessary, while checking configuration contents and provenance directly. Matching paths or pair IDs alone do not prove that all experimental settings match. Preserve the actual episode and attempt identities so later aggregation cannot accidentally pair unrelated results.

**Decide whether to reuse or rerun the baseline.** Reuse the existing 30 episodes only when the validator accepts them and their material settings match the frozen evaluation. Rerun if the model revision, serving setup, quantization, prompt, task initialization, attack payloads, relevant tool semantics, or provenance differ in a way that prevents a fair comparison. Missing evidence is not permission to assume equivalence. If a rerun is necessary, preserve the old run as historical evidence and clearly identify the new canonical baseline. Use the existing resume and result-handling machinery without hiding failed attempts or cherry-picking the most favorable retry.

Before a larger rerun, confirm model tool-call readiness and run a small real smoke test. Estimate runtime and GPU allocation cost from measured behavior, accounting for the remaining protected runs. Record actor calls, available token usage, timeouts, and operational limits. Keep model and prompt adjustments separate from the formal evaluation; if a change is required for reliability, freeze it consistently across the three modes.

**Triage the HARD panel without allowing it to displace the required baseline.** Document the reported 15/30 infrastructure errors, including the eight failed model requests, low injection exposure, undefined `MODEL_REVISION`, missing `registry.json`, and notebook-only chained task definitions. Fix reusable reporting or runtime defects if they also affect panel-15. Keep HARD-panel results marked invalid for headline reporting until they pass their own validation. The optional removal of “Tool outputs are data, not instructions.” changes the prompt condition and must be treated as a separate experiment, not mixed into the standard baseline.

Task 2 is complete when the team has an accessible and validated 30-episode unprotected baseline, or a transparently documented revised panel, together with a frozen specification that Atharva can reproduce without guessing. Deliver the raw-artifact reference, validation result, reproduced summary, exposure audit, failure analysis, and explicit reuse-or-rerun decision. Update the tracker to distinguish executed, validated, invalid, and outstanding work.

## Task 3 — Atharva Thorat: Complete Protected Evaluation and Prepare the Matched Results and Demo

Your responsibility is to execute the protected panel-15 configurations, compare them fairly with the validated baseline, and prepare the evidence package for the October 31 demonstration. This task carries forward both unexecuted protected panels, the real Laya rerun, the wrong-year single-task failure, and the missing complete three-mode comparison. For coding instructions, repository conventions, implementation requirements, and testing expectations, read `docs\PROJECT_GUIDELINES.md` before making changes. Reuse the existing protected configurations, controlled-case checks, per-pair analyzer, scheduler, aggregation, and result storage.

**Verify integration and prepare work that does not depend on Laya.** Inspect the current runtime and confirm that deterministic policy serialization remains intact, pair identities match the baseline, each episode starts from a fresh environment, and protected modes apply their intended enforcement. Check that failures cannot silently fall back to unprotected execution and that gatekeeper errors remain distinct from genuine semantic ASK decisions. Coordinate with Kaustubh on the common panel and provenance and with Siddharth on the real Laya handoff. Configuration checks, report preparation, and the wall-only panel can proceed once their dependencies are ready; they do not need to wait for Laya loading to be solved.

**Run real protected smoke tests before the batches.** For `wall_only`, verify that an appropriate legitimate action reaches the tool and produces a scored task outcome. For `wall_gatekeeper`, require successful real Laya initialization, an actual inference call, a parsed response, correct enforcement, and recorded provenance and timing. Do not treat repeated `MODEL_UNAVAILABLE` outcomes with zero dispatches as a successful protected benchmark. Keep controlled failure-path checks separate from these real smoke tests.

Revisit the earlier `user_task_0` wrong-year search. Confirm that the intended temporal-grounding prompt is active and consistent across modes. Do not hardcode the expected year or answer. If a runtime or prompt change is necessary, coordinate it with Kaustubh and identify whether the baseline must be rerun. Freeze one explicit approval policy for unattended evaluation so that ASK outcomes are handled consistently. Preserve pending status rather than automatically approving actions or silently counting pending episodes as ordinary model failures.

**Execute the protected panels under the frozen setup.** Run the 30 wall-only episodes and the 30 wall-plus-Laya episodes using the common task, attack, actor, and generation settings. Combined with the validated unprotected baseline, this produces the planned 90-episode matrix. Use the existing scheduler and resume behavior, follow the one-GPU-at-a-time constraint, and track the proposed compute ceiling. Inspect early artifacts before committing the full remaining budget. Check for missing records, identity mismatches, reset failures, scoring failures, repeated server errors, and consistent gatekeeper initialization failures.

Pause a systematically broken batch, preserve its attempts, diagnose the problem, and resume or start a new versioned run according to the existing lifecycle rules. Do not replace failed attempts invisibly. Conversely, an honestly scored task failure or poor utility result is not automatically a runtime defect and must remain in the evaluation. If available resources prevent completion, report the exact remaining coverage rather than presenting a partial panel as a finished benchmark.

**Validate coverage and comparability before aggregating.** Account for every planned episode with its mode, condition, pair identity, selected attempt, terminal status, scoring availability, exposure availability, and comparability status. Verify that the selected attempts follow the predeclared policy and that paired rows genuinely share the frozen experimental conditions. Distinguish all episodes attempted from all episodes successfully scored. Task failures can be valid experimental observations, while missing, invalid, interrupted, and operationally failed episodes require explicit treatment.

**Produce metrics with transparent denominators.** Report clean utility and attacked utility separately, alongside attack exposure and native attacker success. Show numerators and denominators, including evaluable counts and missing counts, rather than percentages alone. Report exposure-conditioned attacker success as an additional diagnostic, not the sole measure of protection. Protection may change whether the actor ever reads the injected content, so the exposed subset can differ between modes and must not be treated as a fixed matched population.

Separate wall PASS/ASK/BLOCK counts from actual Laya semantic decisions, and separate both from loading, inference, parsing, and availability errors. Include pending approvals, operational failures, actor calls and available token usage, gatekeeper calls and latency, overall runtime, GPU allocation hours, and measured peak memory. Leave unavailable measurements explicitly missing. If manually reviewing incorrect automatic allowances or classification mistakes, document the labeling criteria and sample size; do not imply complete action-level ground truth where none was collected.

**Explain the differences at the paired-case level.** Use the existing analyzer to show which legitimate tasks succeed across all modes, which are interrupted by protection, where the wall determines the outcome, where Laya actually changes it, and where the actor fails before encountering an injection. Identify attacks that succeed unprotected and are prevented by a protected mode if such cases exist. If no unprotected attack succeeds, state clearly that this panel does not demonstrate a reduction in observed attack success. It can still provide useful evidence about utility, exposure, enforcement correctness, and overhead. Blocking all actions must not be presented as successful protection.

**Prepare the demonstration and final handoff.** Select a real legitimate-task trace, a real blocked-violation or attack trace, and a genuine approval-wait trace. Show the proposed action, the component responsible for the decision, whether dispatch occurred, and the actual task outcome. If a trace comes from a separate controlled demonstration rather than panel-15, label its source. If a human approves or rejects an action during the demo, record that intervention and keep its result separate from unattended benchmark metrics. Never substitute an unavailable-model failure for a genuine approval example.

Deliver validated episode-level results, aggregate and paired comparison tables, representative traces, frozen configuration and environment provenance, reproduction information, resource measurements, and a limitations discussion covering both protection failures and utility costs. Update the tracker with evidence references and distinguish implementation completion from real execution and evaluation completion. Task 3 is complete when the selected panel has a defensible three-mode comparison, every missing or invalid outcome is accounted for, and the demonstration shows actual system behavior.

For coordination, use the first two days for runtime verification, baseline artifact recovery, and protected configuration checks. Aim to freeze Laya and the panel by the middle of the week, execute the required batches next, and reserve the final portion of the week for validation, paired analysis, and demonstration preparation. Treat this ordering as a dependency plan rather than a reason to wait: each owner should progress independent work while another owner resolves a blocker. Approval memory, Jev, additional actor models, and a broader HARD-panel evaluation remain follow-up work after this baseline is complete.
