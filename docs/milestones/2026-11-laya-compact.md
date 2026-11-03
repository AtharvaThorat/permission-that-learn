# November 2026 compact_v1 Laya input

Branch: `data/laya-permission-v1-compact`, based on `main` at `e6d398e`. No merge into `main`.

## Request

Siddharth Magesh (2026-11-03): Laya-Cybersec (`TextCortex/laya-cybersec`) runs at 1,024 tokens including the
classification question, and the laya-permission-v1 contexts are too long. Measure with Laya's tokenizer, then build
a compact version (about 850 context tokens) with a reusable function used identically for fine-tuning and live
inference. Keep the original dataset unchanged and verify that labels and injection evidence survive.

## Measurement before compaction

laya 0.3.28 `encode_text`/`state_room`, `single-v1` question, `max_len` 1024. `TextCortex/laya-cybersec@41fd5a2`
(mmBERT-base, `head_max_len` 256) leaves 882 context tokens; `convaiinnovations/laya@7b928d8` (ModernBERT-large,
`head_max_len` 192, trained at `max_len` 512) leaves 874. Original contexts with the pinned tokenizer: train median
1,002 and max 2,428 tokens, test median 3,089 and max 6,820; 233/300 train and 150/150 test rows exceeded 1,024.
The Wall identity registry was 29% (train) and 58% (test) of tokens; tool history 36% and 23%.

## Delivered

- `compact()` and the `compact_v1` profile in `src/grids/gatekeeper/context.py`, accepted by `GateConfig`, run
  specs, the live adapter and `LayaBackend` (which adds the Wall field as for `evidence_v2`).
- `grids training-data compact | compact-tokens | compact-validate`.
- `docs/results/laya-permission-v1-compact/`: `train.jsonl`, `test.jsonl`, `token_report.json`, `README.md`.
- `tests/unit/core/test_context_compaction.py` (9 tests).

## Verification on 2026-11-03

```bash
python -m grids training-data compact
python -m grids training-data compact-tokens      # Laya environment: laya 0.3.28, torch 2.14.1, transformers 5.20.2
python -m grids training-data compact-validate
python -m ruff check src tests
python -m pytest -q -p no:cacheprovider
```

- Tokens: Laya-Cybersec train median 304 / max 748, test median 439 / max 764; pinned Laya max 622 / 741. No row
  exceeds 850 or its checkpoint's room.
- Evidence: all 119 injected-BLOCK rows keep at least 60 contiguous characters of the injected text together with
  the attack target; 410/412 action values taken from tool outputs keep their source (the two gaps are an amount
  and a date in one injected row whose instruction is kept).
- Same rows, labels and class counts as the original; contexts deterministic; no duplicates.
- Labels: request, action and flags are unchanged by construction; a stratified read of 36 compact rows (6 per
  label per split) plus the gap row found every label still supported by the compact context.

Development found and fixed, before release: excerpts cut away from the attack target on long lines; generic
dates and amounts crowding out injected text; `system_message` and obfuscated cues not detected. The first
working version produced 7 duplicate contexts (clean rows equal to their injected twins); the final has none.

## Limitations

- Evidence selection is heuristic and validated on this dataset only.
- The live controller's Laya input (`gatekeeper_adapter.evaluate`) has no tool history or trusted identities, unlike
  offline replay, so live `compact_v1` states carry no evidence excerpts until that adapter passes them.
- Fine-tuning and real inference with either checkpoint were not run.
