"""Versioned, deterministic reduction of redundant metadata, never action text."""
from copy import deepcopy
import hashlib
import json


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


class ContextError(ValueError):
    def __init__(self, kind, diagnostics):
        super().__init__(kind)
        self.kind, self.diagnostics = kind, diagnostics


def preflight(agent, state, questions, settings, *, profile, max_chars):
    """Use the pinned provider's own encoder, without executing a forward pass."""
    prepared, diagnostics = prepare(state) if profile == 'evidence_v2' else (state, {
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
