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

- same ids, prompts, labels, sources and groups as the original; 300 train and 150 test rows, 100/50 per label
- every context equals compact_v1 of the original context (deterministic), is canonical and validates as a Laya state; request, action, wall and flags unchanged; every target identity has a trust class
- no duplicate contexts or source ids, no label word in any context, no prompt and action pair with two labels, no shared group or near-duplicate prompt across splits; both files load with `datasets`
- injected-BLOCK rows keeping >= 60 chars of the injected text with the attack target: 119/119
- action values taken from tool outputs whose source stays in the compact history: 410/412
- every row fits 850 context tokens and its checkpoint room (table below)

Token counts use each checkpoint's own tokenizer and Laya's `encode_text` and `state_room` (laya 0.3.28) with the
`single-v1` question at `max_len` 1024:

| Checkpoint | Revision | Room for context | Train median / max | Test median / max | Over budget |
|---|---|---:|---|---|---:|
| convaiinnovations/laya | `7b928d82` | 874 | 300 / 622 | 417 / 741 | 0 |
| TextCortex/laya-cybersec | `41fd5a2d` | 882 | 304 / 748 | 439 / 764 | 0 |

## Rebuilding

```bash
pip install -r environments/training-data.txt
python -m grids training-data compact            # reads laya-permission-v1, writes this directory
# in an environment from environments/laya.txt:
python -m grids training-data compact-tokens     # writes token_report.json
python -m grids training-data compact-validate   # checks everything, then writes this README
```

Files:

- `train.jsonl`: `7826e909bd57d138ca7c79e9021674592e658bff3fd88bdaf1765bc95555dc90`
- `test.jsonl`: `ad77da6342c956ae10f89cccdb6e348abd8f79c3e67bb6636d723e249c63e5c1`
- `token_report.json`: `4bf7a7750f8b2f32131157e0eb8278c0e17cddd703ecadbb80c2aeac776001ef`

## Limitations

- Evidence selection is heuristic. It is checked on this dataset's 119 injected rows; unseen injection styles
  with no action value and no agent-addressed wording can lose their text.
- The live controller's Laya input (`gatekeeper_adapter`) carries no tool history or identities today, so live
  compact states have no evidence excerpts until that adapter passes them. Offline replay (`grids evaluate`)
  matches this dataset.
- All limitations of the original dataset apply, including LLM-only label review.
