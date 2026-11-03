"""Versioned, deterministic reduction of redundant metadata, never action text."""
from copy import deepcopy
import hashlib
import json
import re
import unicodedata


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def prepare(state):
    original = json.loads(state)
    result = deepcopy(original)
    facts = result.get('verified_context', {}).get('facts', {})
    metadata = facts.get('metadata', {})
    resources = metadata.get('resources')
    omitted = []
    if 'resource_groups' not in metadata and isinstance(resources, list) and all(isinstance(r, dict) and 'id' in r for r in resources):
        groups = {}
        for i, resource in enumerate(resources):
            details = dict(resource)
            ident = details.pop('id')
            # Opaque content hashes only bind freshness. Full hashes remain in the
            # immutable action evidence and are rechecked by the executor.
            if 'content_hash' in details:
                details.pop('content_hash')
                omitted.append(f'verified_context.facts.metadata.resources[{i}].content_hash')
            groups.setdefault(canonical(details), []).append(ident)
        metadata.pop('resources')
        metadata['resource_groups'] = [{'identities': ids, 'attributes': json.loads(attributes)}
                                       for attributes, ids in sorted(groups.items())]
    diagnostics = {'profile': 'evidence_v2', 'original_characters': len(state),
                   'original_sha256': hashlib.sha256(state.encode()).hexdigest(),
                   'omitted_evidence': omitted, 'essential_evidence_omitted': False,
                   'omission_reason': 'opaque freshness hashes retained in bound action; executor revalidates original facts',
                   'resource_grouping': 'lossless for all remaining fields, including unknown fields'}
    prepared = canonical(result)
    diagnostics['prepared_characters'] = len(prepared)
    return prepared, diagnostics


COMPACT_LIMITS = {'chars': 2300, 'calls': 8, 'call_chars': 120, 'excerpt_chars': 360, 'window': 2, 'value_chars': 80}
COMPACT_TARGET_ARGS = frozenset({'recipient', 'recipients', 'cc', 'bcc', 'user', 'user_email', 'email',
                                 'participants', 'url'})
COMPACT_METADATA = ('account', 'current_day', 'missing')
# Text addressed to the agent. Kept so injected instructions survive compaction;
# label-independent, so benign content that matches is kept too.
INSTRUCTION_CUES = re.compile(r'<information>|###|\b(ignore|disregard|instructions?|important|todo|you must|before you'
                              r'|do the following|system(?:_message)?|assistant|ai model|override|forget|on behalf'
                              r'|bypass|admin(?:_mode)?)\b', re.I)
# Injections hide cue words behind look-alike letters and leetspeak; fold them for detection only.
CUE_FOLD = str.maketrans('аеорсухіјѕԁιορανтκɑɩ013457@$€|+', 'aeopcyxijsdiopavtkaioieastaseit')


def _cues(line):
    return len(INSTRUCTION_CUES.findall(unicodedata.normalize('NFKC', line).lower().translate(CUE_FOLD)))


def _scalars(value):
    if isinstance(value, dict):
        return [v for item in value.values() for v in _scalars(item)]
    if isinstance(value, list):
        return [v for item in value for v in _scalars(item)]
    return [] if value is None or isinstance(value, bool) else [str(value)]


def _target_class(identities, value):
    """The Wall's trust class for one identity; never decided by a model."""
    if not identities:
        return 'unverified'
    if 'native_identities' in identities:
        return identities['native_identities'].get(value, 'unknown')
    from grids.wall.context import WallContext
    fields = {k: identities[k] for k in WallContext.model_fields if k in identities}
    try:
        return WallContext.model_validate(fields).classify(value).value
    except ValueError:
        return 'unverified'


def _excerpts(history, values, budget):
    """Windows of tool output around action values and agent-addressed text, most relevant first."""
    limits = COMPACT_LIMITS
    patterns = [re.compile(re.escape(v), re.I) if len(v) >= 4 else re.compile(r"""['"]%s['"]""" % re.escape(v))
                for v in values if 0 < len(v) <= limits['value_chars']]
    # Identity-like values (IBANs, emails, URLs, names) say where an action came from; short
    # values such as dates and amounts recur on every record and must not crowd them out.
    strong = [p for p, v in zip(patterns, [v for v in values if 0 < len(v) <= limits['value_chars']]) if len(v) >= 8]
    windows = []
    for i, message in enumerate(history):
        if message.get('role') != 'tool' or not message.get('content'):
            continue
        lines = str(message['content']).splitlines()
        spans = []  # [rank, start, end, anchor line, anchor holds an action value, cue count]
        for j, line in enumerate(lines):
            value, cues = any(p.search(line) for p in patterns), _cues(line)
            if value or cues:
                rank = (0 if value and cues else 1 if any(p.search(line) for p in strong) else 2 if cues else 3)
                start, end = max(0, j - limits['window']), min(len(lines), j + limits['window'] + 1)
                if spans and start <= spans[-1][2]:
                    last = spans[-1]
                    # A long window is cut around its anchor; prefer the line naming the action's values.
                    anchor, valued = (j, True) if value and not last[4] else (last[3], last[4])
                    spans[-1] = [min(last[0], rank), last[1], max(last[2], end), anchor, valued, last[5] + cues]
                else:
                    spans.append([rank, start, end, j, value, cues])
        for rank, start, end, anchor, valued, cues in spans:
            text = '\n'.join(lines[start:end])
            if len(text) > limits['excerpt_chars']:
                # Centre on the action value itself when present: one line can hold a whole payload.
                hits = [m.start() for p in patterns for m in [p.search(text)] if m] if valued else []
                centre = min(hits) if hits else len('\n'.join(lines[start:anchor]))
                at = max(0, min(centre - limits['excerpt_chars'] // 2, len(text) - limits['excerpt_chars']))
                text = text[at:at + limits['excerpt_chars']]
            # Injected messages stack several cues; within a rank, denser windows come first.
            windows.append((rank, -cues, -i, start, {'tool': message.get('name'), 'text': text}))
    ordered = sorted(windows, key=lambda w: w[:4])
    # The best window of each kind is reserved first so one kind cannot crowd out another.
    best = {}
    for w in ordered:
        best.setdefault(w[0], w)
    ordered = list(best.values()) + [w for w in ordered if w not in best.values()]
    chosen, used, omitted = [], 0, 0
    for rank, _, order, start, item in ordered:
        cost = len(canonical(item)) + 1
        if used + cost > budget:
            omitted += rank < 3
            continue
        chosen.append((-order, start, item))
        used += cost
    return [item for _, _, item in sorted(chosen, key=lambda c: c[:2])], omitted


def compact(state):
    """compact_v1: request, action and flags verbatim; facts reduced to what an authorization decision uses.

    Identities become the Wall's trust class for each target, metadata keeps referenced
    resources, and history keeps recent calls plus excerpts around action values and
    agent-addressed text within a fixed character budget. Deterministic, label-free and
    tokenizer-free; Laya's own preflight still rejects anything over its token limit.
    """
    prepared, base = prepare(state)
    value = json.loads(prepared)
    context = value.get('verified_context', {})
    facts = context.get('facts', {})
    action = value.get('untrusted_proposed_action') or {}
    arguments = action.get('arguments') or {}
    metadata = facts.get('metadata') or {}
    values = sorted(set(_scalars(arguments)))
    targets = {v: _target_class(facts.get('trusted_identities'), v)
               for key, item in sorted(arguments.items()) if key in COMPACT_TARGET_ARGS for v in _scalars(item)}
    resources = [g for g in metadata.get('resource_groups', []) if set(map(str, g.get('identities', []))) & set(values)]
    history = facts.get('untrusted_history') or []
    calls = [f"{c['function']['name']} {c['function']['arguments']}"[:COMPACT_LIMITS['call_chars']]
             for m in history if m.get('role') == 'assistant' for c in (m.get('tool_calls') or [])]
    kept = {'effects': facts.get('effects', []), 'targets': targets, 'resources': resources,
            **{k: metadata[k] for k in COMPACT_METADATA if metadata.get(k)},
            'history': {'calls': calls[-COMPACT_LIMITS['calls']:], 'earlier_calls': max(0, len(calls) - COMPACT_LIMITS['calls'])}}
    if isinstance(facts.get('permission_policy'), dict) and facts['permission_policy'].get('description'):
        kept['policy'] = facts['permission_policy']['description']
    result = {k: v for k, v in value.items() if k != 'verified_context'}
    result['verified_context'] = {k: v for k, v in context.items() if k != 'facts'}
    result['verified_context']['facts'] = kept
    budget = COMPACT_LIMITS['chars'] - len(canonical(result)) - len(',"evidence":[]')
    evidence, omitted = _excerpts(history, values, budget)
    kept['history']['evidence'] = evidence
    compacted = canonical(result)
    diagnostics = {'profile': 'compact_v1', 'limits': COMPACT_LIMITS, 'original_characters': base['original_characters'],
                   'original_sha256': base['original_sha256'], 'prepared_characters': len(compacted),
                   'evidence_excerpts': len(evidence), 'omitted_evidence': base['omitted_evidence'],
                   'value_excerpts_dropped_for_budget': omitted, 'essential_evidence_omitted': bool(omitted),
                   'omission_reason': 'compaction keeps targets, referenced resources, recent calls and budgeted excerpts'}
    return compacted, diagnostics


class ContextError(ValueError):
    def __init__(self, kind, diagnostics):
        super().__init__(kind)
        self.kind, self.diagnostics = kind, diagnostics


def preflight(agent, state, questions, settings, *, profile, max_chars):
    """Use the pinned provider's own encoder, without executing a forward pass."""
    prepared, diagnostics = prepare(state) if profile == 'evidence_v2' else compact(state) if profile == 'compact_v1' else (state, {
        'profile': profile, 'omitted_evidence': [], 'essential_evidence_omitted': False})
    diagnostics.update(original_characters=len(state), prepared_characters=len(prepared))
    encoder_limit = agent.model.encoder.config.max_position_embeddings
    tokenizer_limit = agent.tok.model_max_length
    effective = settings.get('max_len', agent.cfg.get('max_len', 512))
    diagnostics.update(encoder_limit=encoder_limit, tokenizer_limit=tokenizer_limit,
                       checkpoint_max_len=agent.cfg.get('max_len', 512))
    if effective > encoder_limit or effective > tokenizer_limit:
        raise ContextError('unsupported_context_limit', diagnostics)
    if agent.tok.mask_token and agent.tok.mask_token in prepared:
        raise ContextError('context_reserved_token', diagnostics)
    if max_chars is not None and len(prepared) > max_chars:
        raise ContextError('context_character_overflow', diagnostics)
    ids = list(questions)
    internal = {qid: agent._to_internal(questions[qid]) for qid in ids}
    head = agent._encode_state('', ids, internal, **settings)
    full_head = agent._encode_state('', ids, internal, max_len=encoder_limit, head_max_len=encoder_limit)
    diagnostics['question_head_tokens'] = [len(item['ids']) for item in head]
    diagnostics['complete_question_head_tokens'] = [len(item['ids']) for item in full_head]
    if any(a['ids'] != b['ids'] for a, b in zip(head, full_head)):
        raise ContextError('context_question_truncation', diagnostics)
    original = agent._encode_state(state, ids, internal, **settings)
    encoded = agent._encode_state(prepared, ids, internal, **settings)
    diagnostics.update(original_token_count=original[0]['state_stats']['state_tokens'],
                       prepared_token_count=encoded[0]['state_stats']['state_tokens'],
                       questions={qid: item['state_stats'] for qid, item in zip(ids, encoded)},
                       sequence_tokens=[len(item['ids']) for item in encoded],
                       effective_max_len=settings.get('max_len', agent.cfg.get('max_len', 512)),
                       head_max_len=agent.cfg.get('head_max_len', 192))
    for item in encoded:
        stats = item['state_stats']
        if stats.get('truncated') is not False or stats.get('state_tokens_dropped') != 0:
            raise ContextError('context_overflow', diagnostics)
        options = item.get('options')
        if (not isinstance(options, dict) or not isinstance(options.get('options'), int)
                or options['options'] < 2 or options.get('options_distinct') != options['options']):
            raise ContextError('context_question_truncation', diagnostics)
    return prepared, diagnostics
