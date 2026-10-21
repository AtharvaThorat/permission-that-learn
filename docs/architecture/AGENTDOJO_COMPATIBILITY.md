# AgentDojo compatibility record

Status: **source inspected; runtime compatibility NOT VERIFIED**.

Selected upstream: `ethz-spylab/agentdojo`, exact commit
`089ed468cf3ed0322acc66b0211f26d9d90dbf60`, obtained from GitHub's commit API and
downloaded as individual source files on 2026-10-15. This checkout had no existing
AgentDojo installation/pin to reuse. No Progent fork is combined with it.

The inspected [package metadata](https://github.com/ethz-spylab/agentdojo/blob/089ed468cf3ed0322acc66b0211f26d9d90dbf60/pyproject.toml)
declares distribution `0.1.35` and Python `>=3.10`. Benchmark selection is explicitly
`v1.2.2`. Python 3.13.9 was historically used for standalone Laya; that does not
establish AgentDojo or vLLM compatibility. The existing lock remains unchanged;
new dependency resolution has not been performed. `requests` is explicit in the
integration requirements because the inspected pipeline module imports it.

| Inspected upstream source | Native contract / local adapter |
|---|---|
| `agent_pipeline/base_pipeline_element.py` | `query(query, runtime, env, messages, extra_args)` returns the full tuple; implemented by `integrations/agentdojo/pipeline.py` with fresh defaults |
| `agent_pipeline/agent_pipeline.py`, `basic_elements.py` | Native composition/initialization; our controller initializes only missing system/task records, constructs no stock unguarded executor |
| `types.py` | Dict messages with roles; text blocks use `{type: text, content: ...}`; assistant content may be null with calls; `codec.py` translates explicitly |
| `functions_runtime.py` | `FunctionCall(function, args, id, placeholder_args)`; function registry is `runtime.functions`; `NativeTools` uses each `parameters` Pydantic class |
| `agent_pipeline/llms/openai_llm.py` | Endpoint uses JSON-string arguments and call IDs; our lazy HTTP actor maps the same structured call semantics |
| `agent_pipeline/tool_execution.py` | `tool_result_to_str` formats successes; our codec calls it uniformly across modes, never instantiates `ToolsExecutor` |
| `task_suite/task_suite.py` | Environment initialization, task invocation, up to three retries on null final content, evaluation from transcript and mutated environment |
| `task_suite/load_suites.py`, `default_suites/v1_2_2/` | Version-specific suite selection via `get_suite('v1.2.2', 'workspace')`; task updates reuse workspace tool definitions |
| `default_suites/v1/workspace/task_suite.py` | Workspace registry of 24 named email/calendar/drive tools, mapped below |
| `default_suites/v1/tools/{email,calendar,cloud_drive}_client.py`, `types.py` | Concrete effects, identifiers and fields used by `context.py`; no whole-environment serialization |
| `benchmark.py` | Native `run_task_without_injection_tasks` and `run_task_with_injection_tasks`; our runner passes exact selections |
| `logging.py`, `attacks/base_attacks.py`, `base_tasks.py` | Native trace logging, fixed-file `BaseAttack` subclass, official injection-result semantics |
| `__init__.py`, `agent_pipeline/__init__.py`, `pi_detector.py` | Imports load framework classes; detector loading is in explicit construction, not our factory |

All source paths above are under `src/agentdojo/` at the exact commit; the
[source tree](https://github.com/ethz-spylab/agentdojo/tree/089ed468cf3ed0322acc66b0211f26d9d90dbf60/src/agentdojo)
and committed [`AGENTDOJO_SOURCE_INSPECTION.json`](AGENTDOJO_SOURCE_INSPECTION.json) provide reproducible provenance.
Downloaded inspection files are in ignored `tmp/agentdojo-source/`; they are not a
second installed framework or vendored dependency.

Native `run_function(env, function, kwargs)` returns `(result, error)` and mutates
the supplied environment in place. It resolves direct nested `FunctionCall`
arguments **before** outer schema validation. V1 rejects executable objects at any
depth before reaching it. JSON data is not treated as an executable call. Native
list-string coercion in stock `ToolsExecutor` is deliberately not copied; real
schema validation is shared by all our comparison modes.

The codec preserves native role/call/result order and explicit error fields. It
supports text blocks and plain text, null assistant content with calls, and creates
deterministic episode-local IDs when missing. Duplicate/conflicting IDs fail
explicitly before partial batch dispatch. Thinking/redacted-thinking and multimodal
blocks are unsupported and fail clearly. `placeholder_args` is a ground-truth
runtime concept, not actor authority. Complete existing history is preserved;
unclosed historical batches are rejected rather than replayed as new calls.

The TaskSuite returns the exact active mutated environment. Pending/error outcomes
contain nonempty native final status text, avoiding its null-output retry trigger.
Each independent top-level query is a new episode; no prompt-hash resume exists.

The inspected `functions_stack_trace_from_messages` includes **every assistant
proposal**, even denied calls. Official trace-based checkers may therefore disagree
with our dispatch count. We preserve both; proposals are not deleted to improve
scores. TaskSuite's second returned boolean is injection success when an injection
task exists. The clean path returns constant `True`; it is preserved as
`official_security_field`, while clean `attack_success` is null. No guessed “safe”
polarity is used.

The runner uses native per-task benchmark functions instead of the suite convenience
wrapper, which additionally evaluates injection objectives as standalone user tasks.
That avoids hidden extra episodes while preserving selected-task scoring. The fixed
attack file maps `user task ID -> injection task ID -> native vector ID -> text`;
vectors and selected IDs are validated against the suite. It does not call the
ground-truth pipeline or send attacker objectives/utility labels into our models.

## Reviewed workspace effects and arguments

All argument schemas, including defaults, come from the actual runtime registry.
This table records additional policy effects and identity fields, not replacement
schemas. `*` indicates optional/defaulted native arguments.

| Tool | Native argument fields | Policy effects |
|---|---|---|
| `send_email` | recipients, subject, body, attachments*, cc*, bcc* | outbound |
| `delete_email` | email_id | destructive |
| `get_unread_emails` | none | read + mark_read |
| `get_sent_emails`, `get_received_emails`, `get_draft_emails` | none | read |
| `search_emails` | query, sender* | read |
| `search_contacts_by_name`, `search_contacts_by_email` | query | read |
| `get_current_day` | none | read |
| `search_calendar_events` | query, date* | read |
| `get_day_calendar_events` | day | read |
| `create_calendar_event` | title, start_time, end_time, description*, participants*, location* | calendar_write + outbound |
| `cancel_calendar_event` | event_id | destructive + outbound |
| `reschedule_calendar_event` | event_id, new_start_time, new_end_time* | calendar_write + outbound |
| `add_calendar_event_participants` | event_id, participants | calendar_write + authority_write |
| `append_to_file` | file_id, content | file_write |
| `search_files_by_filename` | filename | read |
| `create_file` | filename, content | file_write |
| `delete_file` | file_id | destructive |
| `get_file_by_id` | file_id | read |
| `list_files` | none | read |
| `share_file` | file_id, email, permission | authority_write |
| `search_files` | query | read |

The participant-addition docstring says it emails participants, but its inspected
implementation only calls `calendar.add_participants` and does not send email.
The mapping follows that implementation and conservatively governs authority
changes. Calendar create/cancel/reschedule do send notifications. Creating an event
also includes the calendar owner, accounted for in resolved recipients. File
attachments resolve file identities; event/compound attachments remain unresolved
in guarded v1 until a reviewed mapping is supplied.

Actor profile: Qwen3-8B, non-thinking, vLLM-compatible Hermes tool parsing, endpoint
explicitly configured. Model ID, local path, served name, revision, tokenizer
template and server version are separate fields. The revision/server/quantization
are unresolved, not invented pins. See the [server environment specification](../../configs/blackbox/ACTOR_SERVER_ENVIRONMENT.md).

Unsupported/unverified: native nested execution, multimodal/thinking content,
event attachments under guarded policy, persistent approvals/resume, arbitrary
new workspace tools without effect review, concurrent use, hard cancellation of
synchronous tools, real email/calendar, dependency resolution and all live
endpoint/model/framework behavior. No model assets or runtime imports were executed
to establish this record.
