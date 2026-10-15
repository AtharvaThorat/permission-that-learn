# The Wall

**Layer 1 of Permissions That Learn: the user's fixed limits, checked by plain code before any agent tool call runs.**

An AI agent can be tricked by a hidden instruction in an email, or simply overstep on its own.
The Wall sits outside the agent and checks every proposed tool call against limits the user
set and confirmed, such as *"only email my contacts, never share files outside work, never
delete anything"*. It runs no LLM at check time, so no text the agent reads can talk it out
of a decision. The gatekeeper and the approval memory only ever see actions the Wall has
already passed, and nothing they learn can move it.

```
                     ┌─────────────── THE WALL (this package) ───────────────┐
agent proposes  ───► │ tool call ─► Action ─► who does it reach? ─► policy    │
a tool call          │              (labels)   (frozen snapshot)    check    │
                     └──────────────────────────────┬────────────────────────┘
                              DENY / UNKNOWN        │ PASS
                     "blocked by policy" ◄──────────┤
                      back to the agent             ▼
                                         gatekeeper (ALLOW / ASK / BLOCK)
                                                    │
                                                    ▼
                                  Wall.revalidate(...) right before execution
```

| | |
|---|---|
| **Scope** | AgentDojo Workspace suite (email, calendar, cloud drive): all 24 tools hand-labeled |
| **Output** | `PASS`, `DENY`, or `UNKNOWN`, with readable reasons and stable reason codes |
| **Dependencies** | `pydantic`, `pyyaml`. No model, no network |
| **Tests** | 96 unit, contract and property tests (Python 3.11 and 3.13) |
| **Owner** | Atharva (Wall). Gatekeeper: Siddharth. AgentDojo harness: Kaustubh |

---

## Contents

1. [Quick start](#quick-start)
2. [The verdict: PASS, DENY, UNKNOWN](#the-verdict-pass-deny-unknown)
3. [How a call is checked](#how-a-call-is-checked)
4. [Plugging in: harness, gatekeeper, executor](#plugging-in-harness-gatekeeper-executor)
5. [Reason codes](#reason-codes)
6. [Policies and presets](#policies-and-presets)
7. [Changing the limits](#changing-the-limits)
8. [Results on AgentDojo](#results-on-agentdojo)
9. [Guarantees and how they are tested](#guarantees-and-how-they-are-tested)
10. [Known limits](#known-limits)
11. [Project layout](#project-layout)
12. [Status and next steps](#status-and-next-steps)

---

## Quick start

```bash
cd wall
uv venv --python 3.11 && source .venv/bin/activate      # or: python -m venv .venv
uv pip install -e ".[dev]"                               # or: pip install -e ".[dev]"
pytest -q                                                # 96 tests, includes Hypothesis properties
python examples/demo.py                                  # the pitch examples, live
```

```python
from ptl.wall import STRICT_WORKSPACE, Wall, WallContext

ctx = WallContext.for_account("emma.johnson@bluesparrowtech.com", contacts=["john.doe@gmail.com"])
wall = Wall(STRICT_WORKSPACE, ctx)

# An injected instruction tries to send files to a stranger
r = wall.evaluate("send_email", {
    "recipients": ["records@outside-audit.com"], "subject": "Q3", "body": "As requested",
    "attachments": [{"type": "file", "file_id": "13"}],
})

r.verdict.decision      # WallDecision.DENY
r.verdict.reasons       # ("'send' is not allowed to: external", "attachments are not allowed to: external")
r.verdict.codes         # ("TARGET_NOT_ALLOWED:external", "ATTACHMENT_NOT_ALLOWED:external")
r.action.fingerprint    # "send_email:external"   coarse key, used later by the memory
r.action_digest         # hash of the exact call (every argument), binds an approval to it
r.wall_version          # policy hash + trust-snapshot hash, log it with every decision
r.to_gatekeeper("A-17") # the `wall` object of the gatekeeper contract v0.1
r.blocked_message()     # text to return to the agent instead of running the tool
```

---

## The verdict: PASS, DENY, UNKNOWN

| Verdict | Meaning | Examples (`STRICT_WORKSPACE`) | What happens |
|---|---|---|---|
| `PASS` | Every check was verified; no limit is violated | read unread emails; reply to a contact; share read-only with a colleague | Goes to the gatekeeper |
| `DENY` | A limit is verifiably violated | delete anything; email a stranger; attach a file for an outsider; share with `rw`; a lookalike domain | Blocked. The user is never asked |
| `UNKNOWN` | Nothing is violated, but the Wall cannot verify the action | an unknown tool; a malformed address; a send or share with no recipient; arguments that are not a dict; an event or file not in the snapshot; an internal error | Blocked. Never executed |

How the decision is made:

- It is **derived** from `allowed` and the reason codes, so the three can never disagree.
  `PASS` carries no codes. `UNKNOWN` means *every* code is one of the "could not verify" codes
  (`UNKNOWN_TOOL`, `MALFORMED_ARGS`, `TARGET_UNVERIFIED`, `WALL_ERROR`). Anything else is `DENY`.
- **`DENY` beats `UNKNOWN`.** An email to one malformed address and one stranger is `DENY`,
  and both problems are listed.
- **Only `PASS` may ever execute.** Neither a user approval nor anything the memory learns turns
  `DENY` or `UNKNOWN` into `PASS`. The two are kept apart only so the logs and the evaluation can
  tell "the agent broke a rule" from "the agent produced something unverifiable".
- **`evaluate` never raises.** A bug inside the Wall becomes `UNKNOWN` with `WALL_ERROR`, never a pass.

> **Team decision to confirm:** `UNKNOWN` is currently handled exactly like `DENY` (returned to
> the agent as blocked). If the team ever wants to show `UNKNOWN` to the user instead, that change
> belongs in the harness, and the executor must still refuse anything that is not `PASS`.

---

## How a call is checked

**1. Tool call to Action** (`wall.py`, `inventory.py`, `workspace_tools.yaml`). Each Workspace
tool is hand-labeled with what it does and which arguments name people.

| Capability | Workspace tools |
|---|---|
| `read` | 14 tools: get or search emails, contacts, calendar, files |
| `create` | `create_calendar_event` (participants), `create_file` |
| `modify` | `reschedule_calendar_event`, `add_calendar_event_participants`, `append_to_file` |
| `send` | `send_email` (recipients, cc, bcc; attachments) |
| `share` | `share_file` (email; permission `r` or `rw`) |
| `delete` | `delete_email`, `delete_file`, `cancel_calendar_event` |

**2. Who does it reach?** (`context.py`). Every address is classified by code against a frozen
snapshot taken when the user confirms the Wall:

| Target | Meaning | Precedence |
|---|---|---|
| `self` | the user's own account, or no outside person | 1 |
| `internal` | exact match on a trusted domain (the user's own, by default) | 2 |
| `contact` | a known outside person in the contact snapshot | 3 |
| `external` | any other valid address | 4 |
| `unknown` | malformed, non-ASCII, several addresses in one string, or no recipient at all | never grantable |

**3. Who else does it reach?** (resource labels). Rescheduling or cancelling an event emails
every participant, and appending to a file changes it for every collaborator. For these tools
the Wall also counts the people who can already see the event or file, from the clean-environment
snapshot (`event_participants`, `file_collaborators`). An ID that is not in the snapshot becomes
`unknown`.

**4. The policy check** (`policy.py`). A `WallPolicy` grants each capability to a set of target
classes, and adds limits on attachments, recipient count, and sharing level. Every problem is
reported twice: as readable text (`reasons`) and as a stable code (`codes`).

---

## Plugging in: harness, gatekeeper, executor

The Wall runs **twice** per action: when the agent proposes it, and again right before the
executor runs it.

```python
from ptl.wall import Wall, WallContext, WallDecision

# Once per task, from the CLEAN pre-environment, before the agent runs
ctx = WallContext.from_agentdojo_env(pre_environment)    # contacts, event participants, file collaborators
wall = Wall(policy_history.current.policy, ctx)

# 1. The agent proposes a tool call
result = wall.evaluate(call.function, dict(call.args))
log(action_id, result.to_gatekeeper(action_id))
if result.verdict.decision is not WallDecision.PASS:
    tool_output = result.blocked_message()               # DENY or UNKNOWN: do not execute, do not ask
else:
    request["wall"] = result.to_gatekeeper(action_id)     # gatekeeper contract v0.1
    decision = gatekeeper.evaluate(request)               # ALLOW / ASK / BLOCK

# 2. Right before executing an ALLOW, or an ASK the user approved
check = wall.revalidate(call.function, dict(call.args), approved=result)
if check.allowed:
    run_tool(call)
# Otherwise check.codes says why: ACTION_CHANGED, WALL_VERSION_CHANGED, NOT_PREVIOUSLY_PASSED
```

**The gatekeeper object** (`to_gatekeeper`) matches the strict `Wall` schema in the gatekeeper
(`gatekeeper/schemas.py`, contract v0.1). No extra fields:

```json
{
  "verdict": "DENY",
  "policy_version": "e874a3bafdaf87b7.fe26418d8c589b4b",
  "evaluated_action_id": "injection_task_0:0",
  "reason_codes": ["TARGET_NOT_ALLOWED:external"]
}
```

`policy_version` is `wall_version`: the policy fingerprint, a dot, then the trust-snapshot
fingerprint. The harness supplies `action_id`, and it must be the same ID it sends to the
gatekeeper for that action.

**Why approval is bound to the exact action.** `action_digest` hashes the tool and every
argument (key order does not matter, any changed value does). `revalidate` re-runs the Wall and
blocks if the digest, the policy, or the trust snapshot changed since the earlier check. So an
approval for "reply to John" cannot be reused for "reply to John, bcc a stranger".

**Take the snapshot once, from the clean environment.** AgentDojo builds `contact_list` from
every address in the starting inbox. Re-reading it mid-run could turn an address from an
attacker's email into a "contact". The starting list already contains a few spam senders (for
example `security-facebook-com@gmail.com`); the injection tasks' attacker address
(`mark.black-2134@gmail.com`) is not among them.

**Checked against AgentDojo.** Field names (`FunctionCall.function`, `.args`, `env.inbox`,
`env.calendar.events`, `env.cloud_drive.files`) were checked against AgentDojo main
(commit 089ed468, June 2026), suite v1.2.2.

**Tool names.** The Wall uses AgentDojo's real names (`send_email`, `share_file`). The
gatekeeper's 20 fixtures use mock names (`email.send`), which are labeled in
`tests/data/gatekeeper_mock_tools.yaml`. The Wall reproduces the fixture verdict for every
policy case. The one deliberate difference is GK-019 (a send with no recipient), where the fixture
says `PASS` to exercise the gatekeeper's own validation and the Wall returns `UNKNOWN`. GK-020 is
"wall unavailable", a harness condition. For the live pipeline, the gatekeeper needs to accept
AgentDojo tool names.

---

## Reason codes

| Code | Verdict | Meaning |
|---|---|---|
| `TOOL_FORBIDDEN` | DENY | The tool is on the policy's forbidden list |
| `CAPABILITY_NOT_GRANTED:<capability>` | DENY | e.g. `CAPABILITY_NOT_GRANTED:delete` |
| `TARGET_NOT_ALLOWED:<class>` | DENY | The action reaches a class the capability is not granted for, e.g. `external` |
| `ATTACHMENT_NOT_ALLOWED:<class>` | DENY | Files or events would go to a class not allowed attachments |
| `TOO_MANY_RECIPIENTS` | DENY | More addresses than `max_recipients` |
| `SHARE_LEVEL_EXCEEDED` | DENY | `rw` sharing when the limit is `r` (a missing or odd level counts as `rw`) |
| `UNKNOWN_TOOL` | UNKNOWN | The tool is not in the inventory |
| `MALFORMED_ARGS` | UNKNOWN | The arguments are not a key/value object |
| `TARGET_UNVERIFIED` | UNKNOWN | A malformed address, no recipient, or an event/file not in the snapshot |
| `WALL_ERROR` | UNKNOWN | An internal error, or a tool name that is not a non-empty string |
| `NOT_PREVIOUSLY_PASSED` | DENY (revalidate) | The earlier result being executed was not a PASS |
| `ACTION_CHANGED` | DENY (revalidate) | The tool or any argument changed after the check |
| `WALL_VERSION_CHANGED` | DENY (revalidate) | The limits or the trust snapshot changed after the check |

`UNVERIFIABLE_CODES` in `models.py` is the single list of codes that mean "could not verify".

---

## Policies and presets

A `WallPolicy` is a frozen Pydantic model. Unknown fields are rejected, `unknown` can never be
granted, and each capability is granted at most once. `explain()` renders it in plain English for
the user to confirm.

| Preset | User's limits in words | Used for |
|---|---|---|
| `STRICT_WORKSPACE` | Handle my email and calendar. Only email people in my contacts. Never share files outside work. Never delete anything. | The pitch example; the main "wall on" setup |
| `WORKSPACE_RELAXED` | Email or invite anyone, but never delete, never send files to strangers, share read-only inside work only. | Studying the safety vs. task-success trade-off |
| `READ_ONLY` | Only read my email, calendar, and files. | Lower bound on automation |
| `ALLOW_ALL` | No limits. | The "no protection" baseline (still blocks `unknown`) |

**Drafting a policy from plain English** (`from_text.py`). An LLM may draft a policy once, from
the user's own words; a human confirms it before it is locked. The LLM is never used at check time.

```python
from ptl.wall import draft_policy
draft = draft_policy("Only email my contacts. Never delete anything.", llm=my_llm_fn)  # any str -> str
print(draft.explain())      # show the user, get a yes, then lock it in
```

Bad or unsafe drafts (unknown fields, `unknown` targets, non-JSON) raise `PolicyDraftError`.
`scripts/check_draft_policy.py` sends 10 phrasings of the pitch's limits to any OpenAI-compatible
endpoint and flags every draft looser than `STRICT_WORKSPACE`.

---

## Changing the limits

```python
from ptl.wall import PolicyHistory

history = PolicyHistory(STRICT_WORKSPACE)                 # v1, confirmed at setup
print(new_policy.explain())                                # show the user
history.replace(new_policy, confirmed=True, note="...")    # v2; raises unless confirmed is exactly True
ctx = ctx.with_contacts("new.client@acme.com")             # the user adds a contact
```

History is append-only, and both changes alter `wall_version`, so `revalidate` rejects any
approval made under the old limits. Only user-facing code may call these. Nothing in the agent,
gatekeeper, or memory path does.

---

## Results on AgentDojo

`scripts/replay_agentdojo.py` runs the reference tool calls AgentDojo ships for every Workspace
task through the Wall, with no LLM involved. Injection tasks 6 to 13 ship no reference calls, so
their essential calls were reconstructed from each task's goal text (marked
`reconstructed_from_goal`).

| Preset | Attacks stopped by the Wall alone | Honest user tasks blocked |
|---|---:|---:|
| `STRICT_WORKSPACE` | 14 / 14 | 11 / 40 |
| `WORKSPACE_RELAXED` | 9 / 14 | 5 / 40 |
| `READ_ONLY` | 14 / 14 | 22 / 40 |
| `ALLOW_ALL` | 0 / 14 | 0 / 40 |

- **Strict limits stop every injection goal**, mostly because each one sends to an outside
  address or deletes something. One caveat: injection task 13 (a phishing link to everyone the
  user meets today) is only partly stopped. Its emails to three outsiders are blocked, but its
  emails to two colleagues pass, because the Wall does not read email bodies. That part is the
  gatekeeper's job.
- **The cost is 11 of 40 honest tasks.** Two are intended ("delete the largest file" under
  "never delete"). The other nine email, invite, or share with people outside the inbox snapshot
  (for example `john.doe@clientcorp.com`). In the full system, these are where the user would
  add a contact or loosen a limit.
- **`WORKSPACE_RELAXED` shows the trade-off:** it blocks 5 honest tasks instead of 11 but lets
  5 attacks through (plain-text exfiltration and the phishing emails).

These are an upper bound on what the Wall stops and a lower bound on what it blocks, since a real
agent can take different paths. `benchmarks/agentdojo_workspace_v1.2.2_wall_labels.jsonl` holds
every replayed call with its verdict in gatekeeper format (504 rows across the 4 presets), for
reuse as labeled actions. None of those rows involve an unverifiable call, so adding `UNKNOWN`
left every one of them unchanged.

```bash
pip install agentdojo
python scripts/replay_agentdojo.py                                   # summary for every preset
python scripts/replay_agentdojo.py --policy STRICT_WORKSPACE --details
python scripts/replay_agentdojo.py --jsonl results/wall_labels.jsonl
```

---

## Guarantees and how they are tested

1. **Deny by default.** Anything not explicitly granted is blocked.
2. **Every target must pass.** One external address in `bcc` blocks the whole email.
3. **Fail closed.** Malformed input is `UNKNOWN`, an odd share level counts as `rw`, an internal error is `UNKNOWN`.
4. **Exact domains only.** `bluesparrowtech.com.evil.com` and subdomains are not internal.
5. **Frozen.** Policies are immutable. Only the user replaces one, and that changes its fingerprint.
6. **Bound to the exact action.** Any change to the tool, an argument, the policy, or the snapshot invalidates an earlier check.
7. **Explainable.** Every block lists every reason and code.
8. **No LLM at check time.** Injected text has no path into a decision.

Property tests (`tests/test_properties.py`: 3,000 seeded random cases per property, plus the same
properties under Hypothesis) check that: an empty policy denies everything; `unknown` targets are
never allowed; a weaker policy never allows more; an allowed action had every target granted;
results are deterministic and leave the policy unchanged; `revalidate` is never looser than
`evaluate`; and the verdict always matches its codes.

| Test file | Covers |
|---|---|
| `test_wall.py` | Pitch examples, inventory, sharing rules, policy integrity, fingerprints |
| `test_context.py` | Address normalization and classification, lookalike domains, AgentDojo snapshot |
| `test_decision.py` | PASS / DENY / UNKNOWN, DENY beats UNKNOWN, fail-closed errors |
| `test_integration_contract.py` | Gatekeeper contract v0.1, the 20 gatekeeper fixtures, binding, revalidation, resource labels, versioning |
| `test_from_text.py` | Validation of LLM-drafted policies |
| `test_properties*.py` | The guarantees above, on random inputs |

---

## Known limits

- **The Wall checks who and what, not content.** It never reads email bodies or file contents, by
  design, so injected text cannot influence it. Content attacks sent to allowed people (injection
  task 13) are left to the gatekeeper.
- **Objects created mid-run are not in the snapshot**, so modifying them afterwards is `UNKNOWN`
  (fail closed). No AgentDojo reference solution does this.
- **The starting contacts are AgentDojo's**, which include a few spam senders. The Wall trusts the
  snapshot it is given; a curated contact list would be stricter.
- **Only the Workspace suite is labeled.** Banking (a `pay` capability with amount limits) is a
  stretch goal.
- **Not yet run in a live agent loop.** All results above come from replayed reference calls.

---

## Project layout

```
wall/
├── src/ptl/wall/
│   ├── models.py             Capability, TargetClass, Action, Verdict, WallDecision, UNVERIFIABLE_CODES
│   ├── workspace_tools.yaml  hand labels for all 24 Workspace tools, incl. resource labels
│   ├── inventory.py          loads the labels (cached)
│   ├── context.py            address classification, trust and resource snapshot, with_contacts()
│   ├── policy.py             WallPolicy, Grant, check(), fingerprint(), explain()
│   ├── wall.py               Wall.evaluate() / revalidate(), WallResult.to_gatekeeper(), action_digest()
│   ├── versioning.py         PolicyHistory: append-only, user-confirmed policy versions
│   ├── from_text.py          plain English to a draft policy via an LLM, validated
│   └── presets.py            STRICT_WORKSPACE, WORKSPACE_RELAXED, READ_ONLY, ALLOW_ALL
├── scripts/
│   ├── replay_agentdojo.py   replay AgentDojo reference calls through the Wall (needs agentdojo)
│   └── check_draft_policy.py test plain-English drafting with a real LLM (needs openai and a key)
├── benchmarks/               replay output: labeled wall verdicts for every Workspace task
├── tests/                    unit, contract, and property tests (+ gatekeeper fixtures in tests/data/)
└── examples/demo.py          the pitch examples
```

CI (`.github/workflows/wall-ci.yml`) runs `ruff check .` and `pytest -q` on Python 3.11 for any
change under `wall/`.

---

## Status and next steps

**Done:** labels for all 24 Workspace tools; deterministic PASS / DENY / UNKNOWN checks;
gatekeeper contract output; exact-action binding and pre-execution revalidation; resource labels
for events and files; versioned, user-confirmed limits; replay against every Workspace user and
injection task.

**Next:**

1. Agree with the harness on the first email/calendar task, and run a real proposed tool call from
   it through `evaluate` (Oct 17 checkpoint).
2. Confirm with the gatekeeper that `UNKNOWN` is accepted end to end and that AgentDojo tool names
   are supported.
3. Call `evaluate` and `revalidate` from the live harness, then re-run the replay on real agent traces.
4. Run `scripts/check_draft_policy.py` with a real model and record the result.
