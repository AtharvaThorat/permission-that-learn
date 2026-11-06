# LLM permission benchmark: LLM alone vs Wall + LLM

**Question.** On the 150 Workspace `test` rows of `AtharvaThorat/grids-laya-permission-v1-compact`, how well do five small
LLMs decide ALLOW, ASK or BLOCK on their own (Configuration A), and with the deterministic Wall deciding first (Configuration
B)? How much compute does the Wall save? Design and checks: [milestone](../../milestones/2026-11-llm-permission-benchmark.md).

**Labels were reviewed by an LLM (Claude), not a person.** Every result is agreement with those labels, not independent
authorization accuracy.

## Provenance

| Item | Value |
|---|---|
| Notebook | `experiments/notebooks/llm_permission_benchmark.ipynb`, run on Colab on 2026-11-03 |
| Repository code used by the run | `main` at `a4af015fee15dc7179a07f28f5221e40da1aba9f` |
| Dataset | revision `aa0d1a1dfd4185c5ead2bec67a9b3865facb48a6`, rows-and-contexts SHA-256 `67dbb6e823164c077c157c72e5aa2011d22dfe09112a4bfc8f33deb39a061554` |
| Prompt | `single-v1` question, SHA-256 `d231fdbd32f99536f07a5a2f0d27d59849b7f5aaf34450404713e00579e6c1ae` |
| Hardware and serving | 1 × NVIDIA A100-SXM4-40GB, Ollama 0.40.14, temperature 0, seed 42, 4,096-token context |
| Models (Ollama digest) | `qwen2.5:7b` `845dbda0ea48`, `qwen3.5:9b-q4_K_M` `56671c2ab938`, `ministral-3:8b-instruct-2512-q4_K_M` `1922accd5827`, `llama3.1:8b` `46e0c10c039e`, `nemotron-3-nano:4b-q4_K_M` `6cc467f05439`; full digests in `run_info.json` |
| Raw run folder | Kaustubh Adhe's Drive, `agentdojo_local_benchmark/llm_permission_benchmark/run_01`. Its `predictions.csv` has every row's decision |

Coverage was 100%: every model answered every row. The Wall's verdict matched the recorded one on 150/150 rows.

## Files

| File | Contents |
|---|---|
| `summary.csv`, `per_class.csv`, `confusion.csv` | Decision metrics on all 150 rows, with counts |
| `a_vs_b.csv` | Paired A vs B comparison per model, exact McNemar |
| `compute.csv`, `compute_saved.csv` | LLM calls, tokens, time, GPU energy and utilization, Wall CPU time, and B's savings |
| `summary_without_policy_refusals.csv`, `a_vs_b_without_policy_refusals.csv` | The same on the 121 rows left after the policy refusals |
| `policy_refusals.csv` | The 29 policy refusals, with what each model decided on its own |
| `run_info.json` | Settings, digests, prompt and dataset identity |
| `charts/1`–`6` | Charts produced in Colab |
| `charts/7_accuracy_without_policy_refusals.png` | Produced locally with the notebook's own policy-refusal cell (its last version, added after the run) on the run's `predictions.csv`; its full-dataset metrics reproduce `summary.csv` exactly |

## Results on all 150 rows

Arrows read A → B. Accuracy out of 150; approved and blocked counts out of 50; `p` is exact McNemar.

| Model | Accuracy | p | BLOCK approved | Injected approved (of 39) | ASK approved | False block |
|---|---|---:|---|---|---|---|
| qwen2.5:7b | 84 → 84 | 1.000 | 2 → 0 | 1 → 0 | 30 → 19 | 11 → 16 |
| qwen3.5:9b | 74 → 84 | 0.002 | 0 → 0 | 0 → 0 | 13 → 21 | 27 → 19 |
| ministral-3:8b | 76 → 73 | 0.648 | 1 → 0 | 1 → 0 | 7 → 6 | 20 → 22 |
| llama3.1:8b | 79 → 83 | 0.659 | 0 → 0 | 0 → 0 | 1 → 0 | 1 → 11 |
| nemotron-3-nano:4b | 69 → 79 | 0.087 | 11 → 1 | 9 → 0 | 39 → 22 | 12 → 19 |
| Wall only | 85 | | 8 | 0 | 25 | 10 |

- No configuration exceeds the Wall alone. Only `qwen3.5:9b`'s change is significant.
- `nemotron-3-nano` accounts for 11 of the 14 BLOCK approvals and 9 of the 11 injected ones in Configuration A.
- The layers complement each other on BLOCK: the Wall alone approves 8 of 50, and every Wall + LLM setup approves 0 or 1.

## Policy refusals, reported separately

The labels judge whether the **user's request** authorized the action; the Wall checks the **user's fixed policy**
(`STRICT_WORKSPACE`: only email contacts, never share outside work, never delete). On 29 rows the request asks for
something the policy forbids, and the Wall refuses a row labelled ALLOW (10) or ASK (19). All 29 are
`TARGET_NOT_ALLOWED:external`, mostly calendar events with external guests. Both sides can be right there, so these rows are
reported separately instead of being counted as Wall errors.

Three more disagreements stay in the scoring: `share_file` on file 26, which the agent created earlier in the same episode.
The Wall reports its facts as missing (UNRESOLVED), a Wall limitation rather than a policy choice.

On the remaining 121 rows:

| Model | Accuracy (of 121) | p |
|---|---|---:|
| qwen2.5:7b | 75 → 84 | 0.004 |
| qwen3.5:9b | 74 → 84 | 0.002 |
| ministral-3:8b | 69 → 73 | 0.388 |
| llama3.1:8b | 59 → 83 | < 0.001 |
| nemotron-3-nano:4b | 60 → 79 | < 0.001 |
| Wall only | 85 | |

Configuration B's ceiling here is 118/121. Leaving out these rows favors the Wall and Configuration B by design, because
they are exactly the rows where the Wall disagrees with the labels, so read this table together with the full one.

## Compute, all five models

| | A: LLM alone | B: Wall + LLM | Saved |
|---|---|---|---|
| LLM calls | 750 | 350 | 53% |
| Tokens | 479,720 | 247,872 | 48% |
| LLM time | 249.8 s | 115.0 s | 54% |
| GPU energy | 10.04 Wh | 4.81 Wh | 52% |

The Wall added 0.14 s of CPU for all 150 rows. GPU energy is the whole board, sampled each second, including idle draw.

## Limitations

- One run, one seed, one A100, 150 rows from one suite.
- Model differences are small against 95% intervals of about ±8 points.
- These are small chat models, not Laya. This does not evaluate the Gatekeeper.
- Policy refusals were defined after seeing the results, using the labels and the Wall's verdicts. They are a scoring
  choice, reported next to the full results, not a replacement for them.
