---
license: other
license_name: mixed-upstream
task_categories:
- text-classification
language:
- en
pretty_name: GRIDS Laya permission decisions v1 (compact_v1)
configs:
- config_name: default
  data_files:
  - split: train
    path: train.jsonl
  - split: test
    path: test.jsonl
---

# GRIDS Laya permission decisions v1, compact_v1

The same 450 rows as [laya-permission-v1](../laya-permission-v1/README.md) (same `id`, `prompt`, `label`,
`source`, `source_id`, `group_id`; 100/50 per label), with `context` reduced by `compact_v1` so every row fits a
1,024-token Laya sequence including the `single-v1` question. The original dataset is unchanged.

Labels are those of the original, reviewed by Claude (an LLM), not a human. See the original card.

## What compact_v1 keeps

`compact_v1` is `compact()` in `src/grids/gatekeeper/context.py`. It is the `compact_v1` input profile of
`LayaBackend`, so the same function runs on training data and at inference. It reads only the state Laya
receives: no labels, no tokenizer, no build metadata. It is deterministic.

- Verbatim: `authentic_user_request`, `untrusted_proposed_action`, `wall`, `confirmation_required`,
  `evidence_complete`, `effects`.
- `targets`: each identity the action touches, mapped to the Wall's trust class (`self`, `internal`, `contact`,
  `external`, `unknown`) instead of the full identity registry.
- `resources`: only the resource groups the action references; `account`, `current_day` and `missing` when present.
- `policy`: the permission policy's one-line description.
- `history.calls`: the last 8 tool calls (120 characters each) and how many earlier calls were omitted.
- `history.evidence`: windows of tool output (two lines either side, at most 360 characters) around action values
  and agent-addressed text, chosen in this order: lines with both, identity-like values (8+ characters), text
  addressed to the agent (detected after folding look-alike and leetspeak characters), short values. The best
  window of each kind is reserved first; the whole context is capped at 2,300 characters.

Pass `context` to Laya unchanged, with `input_profile: compact_v1` and `max_input_tokens: 1024`. Laya's preflight
still rejects any state that would be truncated.

## Validation

{validation}

Token counts use each checkpoint's own tokenizer and Laya's `encode_text` and `state_room` (laya 0.3.28) with the
`single-v1` question at `max_len` 1024:

{tokens}

## Rebuilding

```bash
pip install -r environments/training-data.txt
python -m grids training-data compact            # reads laya-permission-v1, writes this directory
# in an environment from environments/laya.txt:
python -m grids training-data compact-tokens     # writes token_report.json
python -m grids training-data compact-validate   # checks everything, then writes this README
```

Files:

{hashes}

## Limitations

- Evidence selection is heuristic. It is checked on this dataset's 119 injected rows; unseen injection styles
  with no action value and no agent-addressed wording can lose their text.
- The live controller's Laya input (`gatekeeper_adapter`) carries no tool history or identities today, so live
  compact states have no evidence excerpts until that adapter passes them. Offline replay (`grids evaluate`)
  matches this dataset.
- All limitations of the original dataset apply, including LLM-only label review.
