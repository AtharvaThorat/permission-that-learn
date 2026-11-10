# Permission memory: research note and design

Status (2026-11-09):
- **Implemented and CPU-tested:** counting memory, the scoped grant store, and the live hook.
- **Evaluated offline only:** in a simulation with simulated users.
- **Not yet:**
  - run with real users;
  - run in a live benchmark with learning enabled;
  - evaluated with human-reviewed labels.

## 1. What a permission is here

The three layers have separate jobs:

- **Wall:** decides what the agent can ever do. It is deterministic, never learns, and approvals cannot widen it.
- **Gatekeeper (Laya):** judges whether one proposed action fits the authentic request: ALLOW, ASK or BLOCK.
- **Memory:** may only spare the user a question that the Wall and gatekeeper would otherwise ask, and only for
  judgment asks (`NEEDS_CLARIFICATION`, `UNCERTAIN`). Mandatory confirmations, missing evidence and model errors
  always reach the user. Memory sits behind the approval-provider seam, so it never sees a Wall DENY or a BLOCK.

A reusable permission should follow standard authorization practice:
- **Scope.** It names what it covers, as OAuth 2.0 access-token scope does (RFC 6749, section 3.3), with
  fine-grained details such as targets and resources (RFC 9396, Rich Authorization Requests).
- **Binding.** It is bound to the user, the policy version and an expiry.
- **Revocation.** It can be revoked.

Agent-specific work enforces least privilege at the tool-call boundary:
- **Progent** (Shi et al., arXiv 2504.11703) expresses tool-call privilege policies in a DSL, which can be generated
  by an LLM.
- **MiniScope** (Zhu et al., arXiv 2512.11147) derives the minimal permissions a task needs, starts with no access,
  and asks the user to approve extra permissions. It reports fewer confirmation prompts.

Our contribution is not least privilege itself. It is what happens when approvals are remembered across tasks:
- whether interruptions fall;
- whether permissions creep;
- whether careless users make that creep harmful;
- whether a fixed Wall bounds it.

## 2. Why counting creates creep

Counting memory turns repeated approvals into automatic allows. Three properties make that unsafe:

1. **Approvals are not authority.** A user who approved "send to Priya" twice did not say "always send to Priya".
   A careless approval of a harmful action counts the same as a careful one.
2. **Identical actions need different decisions.** In laya-pairs-v1, 106 of 150 rows share a tool and target with
   another row, and the labels inside such groups often differ. Examples:
   - one IBAN payment is labelled ALLOW, ASK and BLOCK in different requests;
   - Dora's Slack invite is labelled ASK five times and ALLOW once.

   A key built from the action alone cannot separate these cases. Only the request can, and judging the request is
   the gatekeeper's job.
3. **Generalization multiplies both effects.** A class-level key ("send to any contact") learned from one approval
   covers attacker targets of the same class. The earlier simulation on the 450-row data
   ([memory-sim](../../results/memory-sim/README.md)) found exactly this outside the Wall.

## 3. Design: grants, not counts (and counting as the comparison arm)

**Decision order.** This is the live order, from the controller and `gatekeeper/policy.py`:
1. The Wall gives anything other than PASS: BLOCK.
2. Laya gives BLOCK: BLOCK.
3. Confirmation is required: ASK the user.
4. Evidence is incomplete: ASK the user.
5. Laya errors: ASK the user.
6. Laya gives ALLOW: ALLOW.
7. A valid scoped grant covers the action: ALLOW.
8. Otherwise: ASK the user.

**`GrantStore`** (`src/grids/core/permissions/memory.py`):
- **Record.** Each user answer to a judgment ask updates per-pattern approval and rejection counts. These are
  preference statistics only.
- **Recommend.** The `offer_after`-th approval of one exact pattern, with no rejection and no live grant, makes an
  offer due ("make this a standing permission?"). An offer creates nothing.
- **Grant.** Only the user's explicit choice creates a grant. Its scope is `exact` (tool, people and resources) or
  `class` (tool and trust classes of the people). It carries the policy version inside its key, an issue time and an
  optional expiry.
- **Revoke.** A rejection of a covered pattern revokes its grant and stops further offers for that pattern. A new
  policy version starts empty, because keys include it.
- **Match.** `covers(exact_key, class_key)` succeeds only under a live grant of the matching scope.

**`GrantApprovalProvider`** uses the store in live runs:
- Offers go to `inner.grant_offer(pending)` when the approval channel supports it.
- The file-based operator channel does not support it, so live runs currently log offers to `memory.jsonl` and
  issue no grants.

**Counting** (`CountingMemory`) stays as the comparison arm:
- auto-allow after k approvals, block after r rejections;
- `exact` or `class` keys.

**Later: a conservative contextual bandit.** It would decide when to offer a grant or when to ask, using features
such as tool, target class, Laya probabilities and approval history. It would run under a constraint to stay no
worse than the fixed policy, as in conservative contextual bandits (Kazerouni et al., NeurIPS 2017,
arXiv 1611.06426). The hard constraints above would stay unchanged. `BanditMemory` (Thompson sampling) exists, but
it is not part of the grants design or of this evaluation.

## 4. Known limits of the design

- **Grants see only the action.** An exact grant issued after a legitimate action also covers an action with the
  same tool, people and resources that is harmful in another request. Laya must catch those first, because the Wall cannot.
- **Partial binding.** Grants bind targets and resource ids, not free text or amounts.
- **Rejections do not stack up.** Only counting memory learns to block after a rejection. Grants can only allow, so
  they do not reduce the repeated questions in which a careless user can slip. Adding remembered rejections to
  grants would tighten and never widen, so it is a safe extension.
- **No live channel for grants.** Live runs need an operator channel that can accept a grant scope before grants can
  be issued outside tests.
