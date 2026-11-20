"""Learning demo: three approvals of one kind, then a new request of that kind is approved without asking (the team's
CountingMemory, keyed by action type), as used by the Colab learner comparison page (cell 5b). Fake laya-cybersec
that answers ASK; the real model is checked by `python -m grids_plugin.learning_demo --laya-cache ...`."""
from support import FakeScanner

from grids_plugin.learning_demo import GROUPS, LearningDemo, group_cases, history_rows, progress_html, result_html
from grids_plugin.session import VERIFIED_CASES, borderline

ASKING = FakeScanner(ask_tools=set(GROUPS))


def test_cases_are_grouped_by_action_type_without_borderline_or_single_cases():
    groups = group_cases()
    assert {tool: len(ids) for tool, ids in groups.items()} == {
        'search_emails': 14, 'search_calendar_events': 14, 'get_file_by_id': 15}
    for tool, ids in groups.items():
        assert all(VERIFIED_CASES[i]['proposed_tool_call']['tool'] == tool and not borderline(i) for i in ids)
    demo = LearningDemo(ASKING)
    # The team's class key: one key per action type, so different requests of one kind share what was learned.
    for ids in groups.values():
        assert len({demo.key(VERIFIED_CASES[i]) for i in ids}) == 1
    assert len({demo.key(VERIFIED_CASES[ids[0]]) for ids in groups.values()}) == 3


def test_three_approvals_then_a_new_request_of_that_kind_is_approved_without_asking():
    demo = LearningDemo(ASKING)
    assert demo.k == 3
    approved = []
    for n in range(3):
        entry = demo.run(demo.next_case('search_emails'))
        assert demo.pending is entry and entry['by'] == 'you' and entry['id'] not in [e['id'] for e in approved]
        demo.answer(True)
        approved.append(entry)
        assert demo.status('search_emails') == (n + 1, 0, 'learned' if n == 2 else 'learning')
    third = demo.run(demo.next_case('search_emails'))   # the 4th request: a new one
    assert third['id'] not in [e['id'] for e in approved] and third['prompt'] != approved[0]['prompt']
    assert demo.pending is None and third['by'] == 'memory' and third['approved'] is True
    assert third['learned_from'] == [e['topic'] for e in approved]
    assert 'Approved by learning' in result_html(demo) and 'Not asked' in result_html(demo)
    # Other kinds learned nothing: a calendar lookup still asks.
    calendar = demo.run(demo.next_case('search_calendar_events'))
    assert demo.pending is calendar
    demo.answer(False)
    # One rejection: memory stops that kind without asking (the team's rule: memory only tightens on rejection).
    stopped = demo.run(demo.next_case('search_calendar_events'))
    assert stopped['by'] == 'memory' and stopped['approved'] is False and demo.pending is None
    assert demo.status('search_calendar_events')[2] == 'stopped'
    assert 'Learned' in progress_html(demo) and 'Stopped' in progress_html(demo)
    assert [row[4] for row in history_rows(demo)] == ['you', 'you', 'you', '⚡ learning (not asked)', 'you',
                                                       '⚡ learning (not asked)']


def test_a_model_allow_is_not_asked_or_learned():
    demo = LearningDemo(FakeScanner())   # answers ALLOW
    entry = demo.run(demo.next_case('get_file_by_id'))
    assert entry['by'] == 'laya' and entry['approved'] and demo.pending is None
    assert demo.status('get_file_by_id') == (0, 0, 'learning')

