"""Laya training data: published files, exact model input, attacker identities, review selection."""
import json
import random

import pytest
from grids.gatekeeper import training_data as td
from grids.gatekeeper.context import canonical


def test_published_dataset_is_valid_and_leak_free():
    problems, _ = td.check(td.Layout().published, load=False)
    assert problems == []


def test_published_readme_states_review_and_matches_files():
    published = td.Layout().published
    readme = (published / 'README.md').read_text(encoding='utf-8')
    assert '**Review:**' in readme and 'DRAFT' not in readme
    for name in ('train.jsonl', 'test.jsonl', 'provenance.jsonl'):
        assert td.sha256(published / name) in readme


def test_context_is_the_exact_laya_input_and_reproducible():
    suite = td.Suite('banking')
    with td.frozen_clock():
        for k, call, messages, env in suite.replay('user_task_3'):
            if k == 1:
                break
        prompt = 'Send 4.00 to GB29NWBK60161331926819 as a refund.'
        first, meta = suite.state(prompt, messages, env, call, k, 'user_task_3')
        again, _ = suite.state(prompt, messages, env, call, k, 'user_task_3')
    state = json.loads(first)
    assert first == again == canonical(state)
    assert state['authentic_user_request'] == prompt and state['wall'] is None
    assert state['untrusted_proposed_action']['tool'] == 'send_money'
    assert meta['confirmation_required'] is True
    identities = state['verified_context']['facts']['trusted_identities']
    assert identities == td.sorted_sets(identities)


def test_frozen_clock_pins_and_restores_agentdojo_time():
    from agentdojo.default_suites.v1.tools import cloud_drive_client
    original = cloud_drive_client.datetime
    with td.frozen_clock():
        assert cloud_drive_client.datetime.datetime.now() == td.FROZEN_NOW
    assert cloud_drive_client.datetime is original


def test_attacker_identity_is_randomized_and_consistent():
    mapping = td.attacker_map('slack', random.Random(3))
    fake = {original: value for original, value, _ in mapping}
    assert fake['fred9246@gmail.com'] != 'fred9246@gmail.com'
    assert fake['Fred'].lower() == fake['fred9246@gmail.com'].split('.')[0]
    swapped = td.swap({'user': 'Fred', 'note': 'Frederick met Fred', 'email': 'fred9246@gmail.com'}, mapping)
    assert swapped['user'] == fake['Fred'] and swapped['note'] == f'Frederick met {fake["Fred"]}'
    assert swapped['email'] == fake['fred9246@gmail.com']


@pytest.mark.parametrize('args, expected', [({'body': '<summary>'}, True), ({'content': 'Two more activities'}, True),
                                            ({'body': 'Hi, i am a bot'}, False), ({'amount': 4.0}, False)])
def test_placeholder_arguments_are_detected(args, expected):
    assert bool(td.placeholder(args)) is expected


def test_mismatch_skips_actions_related_to_the_request():
    assert td.related('Please pay the bill, like last month.', {'function': 'send_money', 'args': {'amount': 4.0}})
    assert td.related('Invite Dora to Slack.', {'function': 'add_user_to_channel', 'args': {'user': 'Dora'}})
    assert not td.related('What is my total spending?', {'function': 'update_password', 'args': {'password': 'x1y2'}})


def test_review_selection_uses_only_reviewed_rows(monkeypatch):
    monkeypatch.setattr(td, 'SPLITS', {'train': ('slack',)})
    monkeypatch.setattr(td, 'TARGET', {'train': 1})
    rows = {f'c{i}': {'cid': f'c{i}'} for i in range(5)}
    decisions = [{'cid': 'c0', 'split': 'train', 'proposed_label': 'ALLOW', 'decision': 'agree', 'final_label': ''},
                 {'cid': 'c1', 'split': 'train', 'proposed_label': 'ALLOW', 'decision': 'change', 'final_label': 'ask'},
                 {'cid': 'c2', 'split': 'train', 'proposed_label': 'BLOCK', 'decision': 'drop', 'final_label': ''},
                 {'cid': 'c3', 'split': 'train', 'proposed_label': 'BLOCK', 'decision': '', 'final_label': ''}]
    cells, problems, counts = td.select_reviewed(rows, decisions)
    assert [r['cid'] for r in cells['train', 'ALLOW']] == ['c0']
    assert [r['cid'] for r in cells['train', 'ASK']] == ['c1']
    assert problems == ['train BLOCK: 0 usable reviewed rows, need 1']
    assert counts == {'agree': 1, 'change': 1, 'drop': 1}
    cells, problems, _ = td.select_reviewed(rows, decisions, draft=True)
    assert [r['cid'] for r in cells['train', 'BLOCK']] == ['c3'] and problems == []
