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
pytest -q                  # 42 tests + Hypothesis property tests
python examples/demo.py    # the pitch examples, live
```

```python
from ptl.wall import STRICT_WORKSPACE, Wall, WallContext

ctx = WallContext.for_account("emma.johnson@bluesparrowtech.com", contacts=["john.doe@gmail.com"])
wall = Wall(STRICT_WORKSPACE, ctx)

r = wall.evaluate("send_email", {"recipients": ["records@outside-audit.com"], "subject": "Q3",
                                 "body": "...", "attachments": [{"type": "file", "file_id": "13"}]})
r.verdict.allowed          # False
r.verdict.reasons          # ("'send' is not allowed to: external", "attachments are not allowed to: external")
r.action.fingerprint       # "send_email:external"  (used later by the memory)
r.policy_fingerprint       # hash of the policy; log it to prove the Wall never changed
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

**3. The policy check** (`policy.py`). A `WallPolicy` grants each capability to a set of
target classes, plus limits on attachments, recipient count, and sharing level.

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

## Plugging into AgentDojo (for the integration work)

Call the Wall from the guarded tool executor, before the gatekeeper:

```python
# once per task, from the CLEAN pre-environment (before the agent runs)
ctx = WallContext.from_agentdojo_env(pre_environment)
wall = Wall(policy, ctx)

# for each tool call the LLM proposes
result = wall.evaluate(tool_call.function, dict(tool_call.args))
if not result.verdict.allowed:
    return_blocked_message(tool_call, result.verdict.reasons)   # do not execute
else:
    pass  # hand result.action to the gatekeeper
```

Confirm AgentDojo's exact class and field names (`FunctionCall.function`, `.args`, the
executor element) against the installed version. This package was written against its
source on GitHub but has not been run inside AgentDojo yet.

Take the contact snapshot once, from the clean environment. AgentDojo builds
`contact_list` automatically from email participants, so re-reading it mid-run could turn
an attacker's address into a "contact".

## Drafting a policy from plain English

```python
from ptl.wall import draft_policy
draft = draft_policy("Only email my contacts. Never delete anything.", llm=my_llm_fn)
print(draft.explain())     # show the user, get a yes, then lock it in
```

`my_llm_fn` is any function `str -> str` (OpenAI, Anthropic, local). Bad or unsafe output
(unknown fields, `unknown` targets, non-JSON) raises `PolicyDraftError`.

## Files

```
src/ptl/wall/
  models.py             Capability, TargetClass, Action, Verdict
  workspace_tools.yaml  hand labels for all 24 Workspace tools
  inventory.py          loads the labels (cached)
  context.py            address normalization + target classification
  policy.py             WallPolicy, Grant, check(), fingerprint(), explain()
  wall.py               Wall.evaluate(tool, args) -> WallResult
  from_text.py          plain English -> draft policy via an LLM, validated
  presets.py            STRICT_WORKSPACE (pitch example), ALLOW_ALL (baseline)
tests/                  unit tests + property tests
examples/demo.py        the pitch examples
```

## Known limits (by design, for now)

- The Wall looks at **who** an action reaches and **what kind** of action it is. It does not
  read email bodies or file contents; that is deliberate, so injected text cannot influence it.
- `append_to_file` and `reschedule_calendar_event` are treated as touching only the user's
  own data. Files or events shared by others are not modeled yet.
- Only the Workspace suite is labeled. Banking (with `pay` and amount limits) is next.

## Next steps for the Wall

1. Run the tests locally with Hypothesis installed (`pytest -q`).
2. Replay real tool calls from baseline AgentDojo runs through `wall.evaluate` and check: no
   unexpected `unknown` targets on normal tasks, and which attacks the Wall alone blocks.
3. Check whether any attacker addresses already appear in the initial `contact_list`.
4. Try `draft_policy` with a real LLM on 10 phrasings of the same limits and compare to `STRICT_WORKSPACE`.
5. Add 2 or 3 more presets for experiments (for example read-only, and email-only).
