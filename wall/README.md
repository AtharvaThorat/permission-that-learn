# Permissions That Learn: the Wall

The Wall is the first layer of the system. Before any tool call runs, the Wall checks it
against the user's fixed limits. It is plain, deterministic Python: no LLM runs at check
time, so a hidden instruction in an email cannot talk its way past it. Learning (the
memory) only ever happens on actions the Wall has already allowed.

```
agent proposes a tool call ──► WALL ──blocked──► "blocked by policy" back to the agent
                                 │ allowed
                                 ▼
                           gatekeeper + memory (other modules)
```

## Quick start

```bash
uv venv --python 3.11 && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest -q                  # 65 tests + Hypothesis property tests
python examples/demo.py    # the pitch examples, live
```

Status: the Wall is complete for the Workspace suite. It labels all 24 tools, checks every call
deterministically, emits the gatekeeper contract, binds approvals to the exact action, revalidates
before execution, versions the user's limits, and has been replayed against every AgentDojo
Workspace user and injection task (results below). It has not yet run inside a live agent loop;
that is the AgentDojo integration work.

```python
from ptl.wall import STRICT_WORKSPACE, Wall, WallContext

ctx = WallContext.for_account("emma.johnson@bluesparrowtech.com", contacts=["john.doe@gmail.com"])
wall = Wall(STRICT_WORKSPACE, ctx)

r = wall.evaluate("send_email", {"recipients": ["records@outside-audit.com"], "subject": "Q3",
                                 "body": "...", "attachments": [{"type": "file", "file_id": "13"}]})
r.verdict.allowed          # False
r.verdict.reasons          # ("'send' is not allowed to: external", "attachments are not allowed to: external")
r.verdict.codes            # ("TARGET_NOT_ALLOWED:external", "ATTACHMENT_NOT_ALLOWED:external")
r.action.fingerprint       # "send_email:external"  (coarse key, used later by the memory)
r.action_digest            # hash of the exact call (every argument); binds an approval to it
r.wall_version             # policy hash + trust-snapshot hash; log it with every decision
r.to_gatekeeper("A-17")    # the `wall` object of the gatekeeper contract v0.1
```

## How it works

**1. Tool call to Action** (`wall.py`, `inventory.py`). Each of the 24 Workspace tools is
hand-labeled in `workspace_tools.yaml` with a capability and the arguments that name people.

| Capability | Workspace tools |
|---|---|
| read | 14 tools (get/search emails, contacts, calendar, files) |
| create | `create_calendar_event` (participants), `create_file` |
| modify | `reschedule_calendar_event`, `add_calendar_event_participants`, `append_to_file` |
| send | `send_email` (recipients, cc, bcc; attachments) |
| share | `share_file` (email; permission `r` or `rw`) |
| delete | `delete_email`, `delete_file`, `cancel_calendar_event` |

**2. Who is it going to?** (`context.py`). Every address is classified by code from a frozen snapshot:

| Target | Meaning | Precedence |
|---|---|---|
| `self` | the user's own account, or no outside person | 1 |
| `internal` | exact match on a trusted domain (the user's own by default) | 2 |
| `contact` | known outside person (in the contact snapshot) | 3 |
| `external` | any other valid address | 4 |
| `unknown` | malformed, non-ASCII, or several addresses in one string | never grantable |

**3. Who else does it reach?** (resource labels). Rescheduling or cancelling an event emails
every participant, and appending to a file changes it for every collaborator. So for these tools
the Wall also counts the people who can already see the event or file, from a snapshot of the
clean environment (`event_participants`, `file_collaborators`). An event or file ID that is not
in the snapshot becomes `unknown` and is blocked. A send or share with no recipient at all is
malformed and also `unknown`.

**4. The policy check** (`policy.py`). A `WallPolicy` grants each capability to a set of
target classes, plus limits on attachments, recipient count, and sharing level. Every violation
is reported twice: as readable text (`reasons`) and as a stable code (`codes`).

## Design rules (the guarantees)

1. **Deny by default.** Anything not explicitly granted is blocked, including unknown tools.
2. **Every target must pass.** One external address in `bcc` blocks the whole email.
3. **Fail closed.** Malformed addresses become `unknown`; a missing or odd share permission is treated as `rw`.
4. **Exact domains only.** `bluesparrowtech.com.evil.com` and subdomains are not internal.
5. **Frozen.** Policies are immutable Pydantic models. Only the user replaces a policy, which changes its fingerprint.
6. **Explainable.** Every block lists every reason, for logs and the demo dashboard.
7. **No LLM at check time.** An LLM only drafts the policy once, from the user's own words, and a human confirms it (`from_text.py`).

These are checked by property tests (`tests/test_properties.py`, 3,000 random cases per
property, plus a Hypothesis version): deny by default, `unknown` always blocked, a weaker
policy never allows more, allowed means every target was granted, and determinism.

## Plugging in (for the AgentDojo harness and the gatekeeper)

The Wall runs twice per action: once when the agent proposes it, and once more right before
the executor runs it.

```python
# once per task, from the CLEAN pre-environment (before the agent runs)
ctx = WallContext.from_agentdojo_env(pre_environment)   # contacts, event participants, file collaborators
wall = Wall(policy_history.current.policy, ctx)

# 1. the agent proposes a tool call
result = wall.evaluate(call.function, dict(call.args))
if not result.verdict.allowed:
    tool_output = result.blocked_message()               # do not execute; never ask the user
else:
    request["wall"] = result.to_gatekeeper(action_id)     # gatekeeper contract v0.1
    decision = gatekeeper.evaluate(request)               # ALLOW / ASK / BLOCK

# 2. right before executing an ALLOW, or an ASK the user approved
check = wall.revalidate(call.function, dict(call.args), approved=result)
if check.allowed:
    run_tool(call)
# check.codes may contain ACTION_CHANGED or WALL_VERSION_CHANGED: re-check from step 1
```

Field names (`FunctionCall.function`, `.args`, `env.inbox`, `env.calendar.events`,
`env.cloud_drive.files`) were checked against AgentDojo main (commit 089ed468, June 2026),
suite v1.2.2.

Take the snapshot once, from the clean environment. AgentDojo builds `contact_list`
automatically from every address in the initial inbox, so re-reading it mid-run could turn an
attacker's address into a "contact". Note that this also means AgentDojo's starting contacts
already include some spam senders (for example `security-facebook-com@gmail.com`); the
attacker address used by the injection tasks is not among them.

**Tool names.** The Wall uses AgentDojo's real tool names (`send_email`, `share_file`). The
gatekeeper's fixtures use mock names (`email.send`, `files.read`). `tests/data/gatekeeper_mock_tools.yaml`
labels the mock tools so the Wall can be tested against the gatekeeper's 20 cases (it matches
all of them; see `tests/test_integration_contract.py`). For the real pipeline the gatekeeper
needs to accept AgentDojo names.

## Changing the limits

```python
history = PolicyHistory(STRICT_WORKSPACE)                 # v1, confirmed at setup
print(new_policy.explain())                                # show the user
history.replace(new_policy, confirmed=True, note="...")    # v2; raises unless confirmed is True
ctx = ctx.with_contacts("new.client@acme.com")             # the user adds a contact
```

Both change `wall_version`, so `revalidate` rejects any approval made under the old limits.
Only user-facing code may call these; nothing in the agent, gatekeeper, or memory path does.

## Drafting a policy from plain English

```python
from ptl.wall import draft_policy
draft = draft_policy("Only email my contacts. Never delete anything.", llm=my_llm_fn)
print(draft.explain())     # show the user, get a yes, then lock it in
```

`my_llm_fn` is any function `str -> str` (OpenAI, Anthropic, local). Bad or unsafe output
(unknown fields, `unknown` targets, non-JSON) raises `PolicyDraftError`.

`scripts/check_draft_policy.py` sends 10 phrasings of the pitch's limits to any
OpenAI-compatible endpoint and flags every draft that is looser than `STRICT_WORKSPACE`.
It has not been run with a real model yet (needs an API key).

## Results on AgentDojo (Wall alone, no LLM)

`scripts/replay_agentdojo.py` takes the reference tool calls AgentDojo ships for every
Workspace task and runs them through the Wall. Injection tasks 6 to 13 ship no reference
calls, so their essential calls are reconstructed from each task's goal text (marked
`reconstructed_from_goal` in the output).

| Preset | Attacks stopped by the Wall | Honest user tasks blocked |
|---|---:|---:|
| `STRICT_WORKSPACE` (pitch limits) | 14 / 14 | 11 / 40 |
| `WORKSPACE_RELAXED` | 9 / 14 | 5 / 40 |
| `READ_ONLY` | 14 / 14 | 22 / 40 |
| `ALLOW_ALL` (no protection) | 0 / 14 | 0 / 40 |

What this shows:

- **Strict limits stop every injection goal**, mostly because they all send to an outside
  address (`mark.black-2134@gmail.com`) or delete. One caveat: injection task 13 (a phishing
  link to everyone the user meets today) is only partly stopped. Its emails to three outsiders
  are blocked, but its emails to two colleagues pass, because the Wall does not read email bodies.
  Catching that is the gatekeeper's job.
- **The cost is 11 of 40 honest tasks.** Two are intended ("delete the largest file" under
  "never delete"). The other nine invite or email people who are not in the inbox snapshot
  (for example `john.doe@clientcorp.com`, `sarah.connor@gmail.com`), or share or attach a file
  to them. In the full system these are where the user would add a contact or loosen a limit.
- **`WORKSPACE_RELAXED` shows the trade-off**: allowing email to anyone blocks 5 tasks
  instead of 11, but lets 5 attacks through (plain-text exfiltration and the phishing emails).

These are upper bounds on what the Wall stops and lower bounds on what it blocks: a real agent
can take different paths. `benchmarks/agentdojo_workspace_v1.2.2_wall_labels.jsonl` holds
every replayed call with its wall verdict in gatekeeper format (504 rows, 4 presets), for
reuse as labeled actions.

## Files

```
src/ptl/wall/
  models.py             Capability, TargetClass, Action, Verdict (reasons + codes)
  workspace_tools.yaml  hand labels for all 24 Workspace tools, incl. resource labels
  inventory.py          loads the labels (cached)
  context.py            address classification + trust/resource snapshot, with_contacts()
  policy.py             WallPolicy, Grant, check(), fingerprint(), explain()
  wall.py               Wall.evaluate() / revalidate(), WallResult.to_gatekeeper(), action_digest()
  versioning.py         PolicyHistory: append-only, user-confirmed policy versions
  from_text.py          plain English -> draft policy via an LLM, validated
  presets.py            STRICT_WORKSPACE, WORKSPACE_RELAXED, READ_ONLY, ALLOW_ALL
scripts/
  replay_agentdojo.py   replay AgentDojo reference calls through the Wall (needs agentdojo)
  check_draft_policy.py test plain-English drafting with a real LLM (needs openai + a key)
benchmarks/             replay output: labeled wall verdicts for every Workspace task
tests/                  unit, integration-contract, and property tests
examples/demo.py        the pitch examples
```

## Known limits

- The Wall looks at **who** an action reaches and **what kind** of action it is. It does not
  read email bodies or file contents; that is deliberate, so injected text cannot influence it.
  Content attacks sent to allowed people (injection task 13) are left to the gatekeeper.
- Events or files the agent creates during a run are not in the snapshot, so modifying them
  afterwards is blocked (fail closed). No AgentDojo reference solution does this.
- AgentDojo's starting contacts are every address in the inbox, including some spam senders.
  The Wall trusts that snapshot as given.
- Only the Workspace suite is labeled. Banking (with `pay` and amount limits) is a stretch goal.

## Remaining for the Wall

1. Run the Hypothesis property tests (`pip install hypothesis`; they skip without it).
2. Run `scripts/check_draft_policy.py` with a real model and record the result.
3. Once the harness exists, call `evaluate` and `revalidate` from it and re-run the replay on
   real agent traces instead of reference calls.
