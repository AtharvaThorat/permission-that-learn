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

CPU only, no real model. A local fake Ollama server returned invented answers, so its metrics mean nothing.

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
  workbook, CSVs and six charts are written. GPU readings were faked too, so `nvidia-smi` parsing is unverified.

Facts about the data, independent of any LLM: the Wall alone agrees with 85/150 labels, passes 70 rows, and stops all 39 injected
BLOCK rows. It approves 8/50 BLOCK and 25/50 ASK rows, and blocks 10/50 ALLOW rows. Because it disagrees with the labels on 32
of the 80 rows it stops, Configuration B cannot exceed **118/150 (78.7%)**. B therefore makes 53% fewer LLM calls (70 against 150).
The real Wall took about 0.16 s of CPU for all 150 rows on a Windows laptop, including rebuilding its policy for every row.

## Limitations

- Real Ollama serving, model downloads, GPU offload and model quality are unverified. The Ollama request format was checked
  against its published API documentation only.
- Labels are LLM-reviewed, so results measure agreement with them, not independent authorization accuracy.
- GPU energy covers the whole board and includes its idle draw. Tokens are as Ollama reports them, and its prompt cache
  may reduce the prompt tokens it reports; cached counts are saved alongside.
- One seed and 150 rows from one suite; rows come from a Workspace-only split.
- These models are not Laya: this does not evaluate the Gatekeeper, and uses no `exact_time_conflict` rule.
- Ollama tags can change upstream. The recorded digest detects this but does not pin the download.
