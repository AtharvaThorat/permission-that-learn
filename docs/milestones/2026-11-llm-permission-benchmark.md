# November 2026 LLM permission benchmark

Branch: `03_Nov_LLM_Permission_Benchmark`, based on `main` at `a4af015`. No merge into `main`.

## Request

Kaustubh Adhe (2026-11-03): benchmark five small LLMs on the 150 `test` rows of
`AtharvaThorat/grids-laya-permission-v1-compact`, without running AgentDojo. Configuration A is the LLM alone;
Configuration B is the deterministic Wall followed by the LLM. Colab notebook, A100 or T4, with metrics, charts and
results saved to Drive.

## Delivered

`experiments/notebooks/llm_permission_benchmark.ipynb`. No source file changes. Its code imports `grids.wall`,
`grids.evaluation.metrics` and the `single-v1` question rather than copying them. There is no CLI for this because
`grids evaluate` needs a captured dataset and a Laya backend, so this notebook holds its own loop, an exception to the
notebook guideline made at the requester's direction.

- **Data:** rows are loaded from Hugging Face and must equal `docs/results/laya-permission-v1-compact/test.jsonl`.
- **Wall:** rebuilt per row from the policy, trusted identities and facts in the original `laya-permission-v1` context,
  with `resource_groups` expanded back to `resources`. The notebook stops unless every verdict, reason and flag equals
  `provenance.jsonl`.
- **Configuration B:** follows the `wall_gatekeeper` comparator: a non-PASS verdict decides without an LLM call, and on
  PASS the LLM sees the verdict in the row's `wall` field.
- **Models** (Ollama, chosen for distinct families and to fit a 16 GB T4): `qwen2.5:7b`, `qwen3.5:9b-q4_K_M`,
  `ministral-3:8b-instruct-2512-q4_K_M`, `llama3.1:8b`, `nemotron-3-nano:4b-q4_K_M`. The same quantized files run on
  every GPU; digests are recorded.
- **Recovery:** each row is written as it finishes. Re-running resumes, and refuses to mix a changed prompt, dataset
  or model file into an existing run.
- **Metrics:** repository confusion matrix and rates with counts, plus macro-F1, Wilson intervals, coverage, an injected-BLOCK
  slice, exact McNemar and latency. Rows without a usable answer lower coverage and are not scored.
- **Compute (requested by Siddharth Magesh):** per model and configuration: LLM calls, tokens and seconds; GPU energy,
  utilization and peak memory, sampled from `nvidia-smi` each second; and the Wall's CPU seconds. A table gives what B saves
  against A. Time and energy savings appear only when A and B ran on the same GPU. Energy stays empty unless every row was
  measured. Model loading is excluded.

## Verification on 2026-11-03

Before the real run, on CPU with no real model. A local fake Ollama server returned invented answers, so its metrics mean nothing.

```bash
python -m ruff check src tests
python -m pytest -q -p no:cacheprovider
```

- In an environment with only the repository's base dependencies and no AgentDojo, Laya or torch installed, the real Wall
  matched `provenance.jsonl` on verdict, reason, confirmation and evidence for 150/150 rows.
- The Hugging Face rows equal the repository's compact `test.jsonl`.
- With the fake server, the notebook's own cells ran end to end. Checked: an interrupted run and a cut-off last line resume to
  exactly 150 unique rows; a finished run sends no more requests; user messages equal the row context, plus the Wall field
  in B; B calls the LLM on 70 rows, all PASS; `think` is sent only to thinking-capable models; errors and unparseable
  replies lower coverage; an interrupted run keeps its compute measurement; a missing power reading stays missing;
  workbook, CSVs and six charts are written. GPU readings were faked in this rehearsal; the real run below measured them.

Facts about the data, independent of any LLM: the Wall alone agrees with 85/150 labels, passes 70 rows, and stops all 39 injected
BLOCK rows. It approves 8/50 BLOCK and 25/50 ASK rows, and blocks 10/50 ALLOW rows. Because it disagrees with the labels on 32
of the 80 rows it stops, Configuration B cannot exceed **118/150 (78.7%)**. B therefore makes 53% fewer LLM calls (70 against 150).
The real Wall took about 0.16 s of CPU for all 150 rows on a Windows laptop, including rebuilding its policy for every row.

## Real run on 2026-11-03

Colab A100-SXM4-40GB, Ollama 0.40.14, repository code at `a4af015`, seed 42, `RUN_NAME` `run_01`. Coverage 100%: no errors or
unparseable replies, and all models ran fully on the GPU. Outputs are saved in the notebook (commit `735ecc8`); the raw run
folder is on the requester's Drive under `agentdojo_local_benchmark/llm_permission_benchmark/run_01`. Charts, summary CSVs,
digests and settings are in [docs/results/llm-permission-benchmark](../results/llm-permission-benchmark/README.md).

Counts are out of 150 (accuracy) and 50 (approved rows). Arrows read A → B; `p` is exact McNemar on accuracy.

| Model (digest) | Accuracy | p | BLOCK approved | ASK approved | False block | LLM seconds | GPU Wh |
|---|---|---:|---|---|---|---|---|
| `qwen2.5:7b` (`845dbda0ea48`) | 84 → 84 | 1.000 | 2 → 0 | 30 → 19 | 11 → 16 | 31.5 → 12.4 | 1.58 → 0.61 |
| `qwen3.5:9b-q4_K_M` (`56671c2ab938`) | 74 → 84 | 0.002 | 0 → 0 | 13 → 21 | 27 → 19 | 71.5 → 31.6 | 2.78 → 1.30 |
| `ministral-3:8b-instruct-2512-q4_K_M` (`1922accd5827`) | 76 → 73 | 0.648 | 1 → 0 | 7 → 6 | 20 → 22 | 40.1 → 20.8 | 2.07 → 0.99 |
| `llama3.1:8b` (`46e0c10c039e`) | 79 → 83 | 0.659 | 0 → 0 | 1 → 0 | 1 → 11 | 30.8 → 15.8 | 1.34 → 0.79 |
| `nemotron-3-nano:4b-q4_K_M` (`6cc467f05439`) | 69 → 79 | 0.087 | 11 → 1 | 39 → 22 | 12 → 19 | 76.0 → 34.4 | 2.27 → 1.13 |
| Wall only (no LLM) | 85 | | 8 | 25 | 10 | 0 | 0 |

- **Accuracy:** no configuration exceeded the Wall alone (85/150). Only `qwen3.5:9b` changed significantly with the Wall in
  front (McNemar p = 0.002).
- **Harmful approvals:** across all models, approved BLOCK rows fell from 14 to 1 of 250, and approved injected BLOCK rows from
  11 to 0 of 195. `nemotron-3-nano` accounts for 11 of the 14 and 9 of the 11 without the Wall.
- **The layers complement each other on BLOCK:** the Wall alone approves 8/50 BLOCK rows, every Wall + LLM setup 0 or 1.
- **Low approval is not always judgment:** alone, `qwen3.5:9b` decides BLOCK on 113/150 rows and `llama3.1:8b` decides ASK on
  118/150, including 43/50 ALLOW rows.
- **ASK is the weak class:** correct ASK alone is 7, 1, 11, 49 and 0 of 50, and 9, 7, 10, 31 and 6 of 50 with the Wall.
- **Compute, all five models, A → B:** LLM calls 750 → 350 (53% fewer), tokens 479,720 → 247,872 (48%), LLM time 249.8 s → 115.0 s
  (54%), GPU energy 10.04 Wh → 4.81 Wh (52%), measured on the whole GPU board. Per model, energy savings range from 42% to
  62%. The Wall added 0.14 s of CPU.
- **Wall against labels:** of the 80 rows the Wall decides, it disagrees with the labels on 32. These are not label errors.
  Atharva Thorat's review (2026-11-05), confirmed on the data:
  - **29 are policy refusals.** All are `TARGET_NOT_ALLOWED:external`: `STRICT_WORKSPACE` forbids an external recipient the
    request asks for, on 10 ALLOW and 19 ASK rows. The labels answer "did the request authorize this", the Wall "does the policy
    allow it", so relabeling would not reconcile them.
  - **3 are a Wall gap.** They are `share_file` on a file created earlier in the same episode, which the Wall reports as
    missing facts.

## Policy refusals, reported separately (2026-11-06)

Kaustubh Adhe chose to report the policy refusals separately instead of using policy-aware labels or rerunning with
`WORKSPACE_RELAXED`. The notebook gained one section after section 11. Its existing cells and their Colab outputs are unchanged.
The section was run locally on the real run's `predictions.csv`, with the Hugging Face rows and the Wall rebuilt as in Colab.
Dataset and prompt hashes equal `run_info.json`, and the re-scored full-dataset metrics and paired table equal the Colab files
exactly.

On the 121 remaining rows, Wall + LLM is significantly more accurate than the LLM alone for four models: `qwen2.5` 75 → 84
(p = 0.004), `qwen3.5` 74 → 84 (p = 0.002), `llama3.1` 59 → 83 and `nemotron-3-nano` 60 → 79 (both p < 0.001). `ministral-3`
is the exception, 69 → 73 (p = 0.388). The Wall alone still scores 85/121, and B's ceiling there is 118/121. Leaving out these rows
favors the Wall and B by design, so this view is reported next to the full-dataset results, not instead of them. The
3 Wall-gap rows stay in the scoring.

## Limitations

- One A100 run. T4 serving is unverified, and the differences between models are small against 95% intervals of about ±8 points.
- Labels are LLM-reviewed, so results measure agreement with them, not independent authorization accuracy.
- GPU energy covers the whole board and includes its idle draw. Tokens are as Ollama reports them, and its prompt cache
  may reduce the prompt tokens it reports; cached counts are saved alongside.
- One seed and 150 rows from one suite; rows come from a Workspace-only split.
- These models are not Laya: this does not evaluate the Gatekeeper, and uses no `exact_time_conflict` rule.
- Policy refusals were defined after seeing the results, using the labels and Wall verdicts. Scoring the combined system
  against policy-aware labels, or a `WORKSPACE_RELAXED` rerun, remain open alternatives.
- The Wall cannot verify files created earlier in the same episode. That is a Wall fix outside this task.
- Ollama tags can change upstream. The recorded digest detects this but does not pin the download.
