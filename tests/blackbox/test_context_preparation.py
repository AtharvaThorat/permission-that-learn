import json
from types import SimpleNamespace
import pytest

from gatekeeper.context import prepare
from gatekeeper.context import preflight, ContextError


class EncoderFixture:
    cfg = {'max_len': 512, 'head_max_len': 192}
    model = SimpleNamespace(encoder=SimpleNamespace(config=SimpleNamespace(max_position_embeddings=8192)))
    tok = SimpleNamespace(model_max_length=8192, mask_token='[MASK]')

    def _to_internal(self, question):
        return question

    def _encode_state(self, state, ids, internal, **settings):
        count = len(state.split())
        used = min(count, settings.get('max_len', 512) - 100)
        return [{'ids': list(range(used + 100)), 'options': {'options': 3, 'options_distinct': 3},
                 'state_stats': {'state_tokens': count, 'state_tokens_used': used,
                                 'state_tokens_dropped': count - used, 'truncated': used < count}} for _ in ids]


def test_preflight_rejects_overflow_before_inference_and_records_counts():
    with pytest.raises(ContextError) as failure:
        preflight(EncoderFixture(), 'evidence ' * 700, {'decision': {}}, {}, profile='full_evidence', max_chars=None)
    assert failure.value.kind == 'context_overflow'
    assert failure.value.diagnostics['original_token_count'] == 700
    assert failure.value.diagnostics['prepared_token_count'] == 700


def test_preflight_preserves_short_state_and_checks_actual_encoder_limit():
    state = 'exact short evidence'
    prepared, diagnostics = preflight(EncoderFixture(), state, {'decision': {}}, {}, profile='full_evidence', max_chars=None)
    assert prepared == state and diagnostics['prepared_token_count'] == 3
    with pytest.raises(ContextError, match='unsupported_context_limit'):
        preflight(EncoderFixture(), state, {'decision': {}}, {'max_len': 9000}, profile='full_evidence', max_chars=None)
    with pytest.raises(ContextError, match='context_reserved_token'):
        preflight(EncoderFixture(), '[MASK]', {'decision': {}}, {}, profile='full_evidence', max_chars=None)


def test_preparation_preserves_action_and_all_authorization_attributes():
    state = {'authentic_user_request': 'Read the records; do not send anything.',
             'untrusted_proposed_action': {'tool': 'search', 'arguments': {'query': 'exact', 'recipient': 'a@example.org'}},
             'wall': {'verdict': 'PASS', 'policy_version': 'p1'},
             'verified_context': {'evidence_complete': False, 'confirmation_required': True,
                 'facts': {'effects': ['read'], 'metadata': {'missing': ['approval'], 'recipients': ['a@example.org'],
                     'resources': [{'id': str(i), 'label': 'private', 'source': 'verified',
                                    'content_hash': str(i) * 64, 'unknown_critical_field': ['keep']} for i in range(100)]}}}}
    original = json.dumps(state)
    prepared, diagnostics = prepare(original)
    result = json.loads(prepared)
    assert result['authentic_user_request'] == state['authentic_user_request']
    assert result['untrusted_proposed_action'] == state['untrusted_proposed_action']
    assert result['wall'] == state['wall']
    assert not result['verified_context']['evidence_complete']
    metadata = result['verified_context']['facts']['metadata']
    assert metadata['missing'] == ['approval'] and metadata['recipients'] == ['a@example.org']
    group = metadata['resource_groups'][0]
    assert group['identities'] == [str(i) for i in range(100)]
    assert group['attributes']['unknown_critical_field'] == ['keep']
    assert len(diagnostics['omitted_evidence']) == 100
    assert not diagnostics['essential_evidence_omitted']
    assert len(prepared) < len(original)
    assert prepare(original) == (prepared, diagnostics)
    assert json.dumps(state) == original


def test_unknown_evidence_is_never_pruned_to_force_fit():
    state = {'verified_context': {'facts': {'authorization': 'x' * 100000}}}
    prepared, diagnostics = prepare(json.dumps(state))
    assert json.loads(prepared) == state
    assert diagnostics['omitted_evidence'] == []


def test_existing_resource_groups_are_not_overwritten():
    state = {'verified_context': {'facts': {'metadata': {
        'resources': [{'id': 'one', 'content_hash': 'bound'}],
        'resource_groups': [{'authorization': 'preserve this evidence'}]}}}}
    prepared, diagnostics = prepare(json.dumps(state))
    assert json.loads(prepared) == state
    assert diagnostics['omitted_evidence'] == []
