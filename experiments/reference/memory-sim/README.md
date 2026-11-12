> Historical study. Per-seed CSV tables are archived in Git at `46aed6a`; retained aggregates and predictions remain here.

# Approval memory: offline simulation (run_01)

The question: does an approval memory that learns from a user's answers cut interruptions without letting
permissions creep, and does the Wall keep that creep away from harmful actions when the user is careless?
This compares the proposal's four setups on the same action streams. No model or GPU is involved.

## Provenance

- Code: branch `feature/approval-memory`, based on `main` at `a4af015`.
- Command: `python -m grids memory simulate --seeds 50 --passes 3 --output results/memory-sim/run_01`.
  A second run into a new directory produced byte-identical files.
- Inputs (sha256 values in `run.json`): `experiments/reference/laya-permission-v1/provenance.jsonl` and
  `experiments/reference/laya-permission-v1-compact/{train,test}.jsonl`. These are 450 actions, 150 per label, from three suites
  (banking 139, slack 161, workspace 150). 119 BLOCK rows are injected attacks.
- Files: `summary.csv` (mean and 95% CI per setup, learner, granularity and user), `runs.csv` (one row per seed),
  `curves.csv` (questions and auto-allowed patterns after each pass) and `run.json` (settings and input hashes).

## Method

- **Stream.** One simulated user meets one suite's actions in a seeded random order, three times over (three
  passes). Actions therefore recur, as in the proposal's example of the same request on Monday and Wednesday.
  Memory starts empty for each user. Every number below adds up the three suites, so each stream has 1,350 actions:
  450 per pass. Means are over 50 seeds.
- **Decision path.** It follows the live controller:
  1. The Wall: anything other than PASS is blocked.
  2. The rules gatekeeper: reads are allowed, destructive actions are blocked, anything else is asked.
  3. Forced asks: confirmation required, or incomplete evidence.
  4. Memory, which answers only judgment asks (`NEEDS_CLARIFICATION`, `UNCERTAIN`) and otherwise passes the
     question to the user.
- **Wall verdicts and confirmation flags** are the replayed ones recorded in the dataset provenance.
- **Users.**
  - A careful user approves ALLOW and ASK actions and rejects BLOCK actions.
  - A careless user also approves a BLOCK action with probability 10%, 20% or 40%.
  - The careless moments are the same in every setup, so setups are compared on paired streams.
- **Learners.**
  - `counting`: allows a pattern after 2 approvals with no rejection, and blocks it after 1 rejection.
  - `bandit`: Beta Thompson sampling. It allows when a sample exceeds `1 - ask_cost / wrong_allow_cost` = 0.9, and
    still asks 10% of the time.
- **Granularity.**
  - `exact`: tool plus target identities plus resource ids.
  - `class`: tool plus target trust classes.
- **Labels** drive only the simulated user and the metrics. The learner receives a pattern key and a yes or no,
  and a test checks this.

## Results, careless user at 20% (totals over 1,350 actions)

| Setup | Learner, key | Questions | Attacks executed | Harmful actions executed | Wrong auto-allows | False blocks |
|---|---|---:|---:|---:|---:|---:|
| No protection | none | 0 | 357 | 450 | 0 | 0 |
| Fixed rules (Wall + rules) | none | 474 | 5.4 | 18.7 | 0 | 126 |
| Learning, no Wall | counting, exact | 188.8 | 29.6 | 77.7 | 53.2 | 38.9 |
| Learning, no Wall | counting, class | 46.1 | 96.1 | 143.3 | 141.2 | 78.2 |
| Learning, no Wall | bandit, exact | 859.5 | 72.1 | 104.3 | 24.0 | 0 |
| **Learning inside the Wall** | **counting, exact** | **170.5** | **1.2** | **26.4** | **23.6** | **144.9** |
| Learning inside the Wall | counting, class | 151.8 | 9.2 | 36.3 | 34.2 | 151.1 |
| Learning inside the Wall | bandit, exact | 390.8 | 5.5 | 23.4 | 6.0 | 126 |

Notes on the columns:
- "Harmful actions executed" counts every BLOCK-labeled action that ran, whether it was an attack or a task mismatch.
- "Wrong auto-allows" counts BLOCK-labeled actions that memory allowed without asking.
- Rows that carry a 95% CI in `summary.csv`:
  - learning inside the Wall, counting exact, attacks executed: Â±1.5;
  - learning without the Wall, counting class, attacks executed: Â±18.3.

Questions per pass (careless 20%):

| Setup | Pass 1 | Pass 2 | Pass 3 |
|---|---:|---:|---:|
| Fixed rules | 158 | 158 | 158 |
| Learning inside the Wall, counting exact | 80.5 | 45 | 45 |
| Learning inside the Wall, bandit exact | 139.6 | 127.8 | 123.4 |
| Learning, no Wall, counting exact | 169.2 | 19.6 | 0 |
| Learning, no Wall, counting class | 46.1 | 0 | 0 |

How results change with the careless rate (counting, exact):

| Careless rate | Inside the Wall: attacks | No Wall: attacks | Fixed rules: attacks |
|---|---:|---:|---:|
| 0% (careful) | 0 | 0 | 0 |
| 10% | 0.6 | 13.3 | 2.7 |
| 20% | 1.2 | 29.6 | 5.4 |
| 40% | 4.0 | 79.5 | 10.5 |

## Findings

1. **Learning inside the Wall cuts questions by 64%** (474 to 170.5), with attacks executed staying low (1.2 at 20%
   careless, 4.0 at 40%). In both cases that is below fixed rules (5.4 and 10.5). After the first pass, the 45
   questions left per pass are the forced confirmations (for example, payments) that memory never answers.
2. **Without the Wall, permission creep reaches attacks.**
   - With class keys, memory stops asking after the first pass, and attacks executed reach 96.1 at 20% careless.
   - Even a careful user lets 57.1 attacks through (CI Â±13.7). One approval of a legitimate send to an external
     contact teaches "send to external contacts", and attacker targets share that class.
   - With exact keys and a careful user, the attack count is 0, but careless approvals still grow it to 29.6 and 79.5.
3. **The bandit asks more and creeps less.** It is still learning after three passes (139.6 to 123.4 questions per
   pass), which leaves it with few auto-allowed patterns. Without the Wall it executes 72.1 attacks at 20% careless,
   because the user is asked so often and approves carelessly. Fewer automatic decisions do not mean fewer harmful
   outcomes.
4. **Wrong auto-allows inside the Wall are task mismatches, not attacks.**
   - With a careful user, 17.6 BLOCK actions are auto-allowed, with 0 attacks among them.
   - These are BLOCK rows whose action is byte-identical to an action that a different task legitimately needed.
     Inside the Wall, 27 BLOCK rows reach memory and fall under 8 exact patterns. 7 of those patterns also cover
     ALLOW or ASK rows, and none of the 7 covers an attack.
   - A memory keyed only on the action cannot tell them apart, and the rules gatekeeper cannot either.
   - Telling them apart needs the user's request, which is Laya's job. This is the main limit of action-keyed memory.
5. **Tightening after a rejection costs false blocks.** Inside the Wall, counting raises false blocks from 126 to
   144.9: one rejection of a shared pattern also blocks later legitimate uses of it.
6. **The Wall itself blocks legitimate work.** The 126 false blocks under fixed rules are 42 ALLOW-labeled actions
   per pass that the Wall denies (29) or cannot resolve (13). That is 28% of ALLOW rows, and it is the price of the
   Wall in this dataset. It is a target for Wall policy review, independent of memory.

## Limits

- **Labels.** The labels were reviewed by an LLM (Claude), not by people.
- **Users.** The simulated users are a behaviour model. Real users err in correlated ways, for example by approving
  everything when tired.
- **Gatekeeper.** The rules gatekeeper is a deterministic stand-in for Laya. Laya's quality is not measured here.
- **Repetition.** Results depend on the three-pass repetition assumption. With one pass, memory has almost nothing to
  reuse. How often real actions recur was not measured.
- **Dataset.** The 450 actions are a balanced training set, not a natural stream. Its proportions of attacks and
  repeats are not those of real use.
- **Live hook.**
  - It is implemented and CPU-tested through the controller fixtures, but not run with real models.
  - In a live run with parallel episodes, the order in which memory learns depends on scheduling.
