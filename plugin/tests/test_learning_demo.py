"""Learning demo: two approvals of one kind, then a new request of that kind is approved without asking (the team's
CountingMemory, keyed by action type). Fake laya-cybersec that answers ASK; the real model is checked by
`python -m grids_plugin.learning_demo --laya-cache ...`."""
from support import FakeScanner

from grids_plugin.app import build_app
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


def test_two_approvals_then_a_new_request_of_that_kind_is_approved_without_asking():
    demo = LearningDemo(ASKING)
    first = demo.run(demo.next_case('search_emails'))
    assert demo.pending is first and first['by'] == 'you'
    demo.answer(True)
    assert demo.status('search_emails') == (1, 0, 'learning')
    second = demo.run(demo.next_case('search_emails'))
    assert demo.pending is second and second['id'] != first['id']
    demo.answer(True)
    assert demo.status('search_emails') == (2, 0, 'learned')
    third = demo.run(demo.next_case('search_emails'))
    assert third['id'] not in (first['id'], second['id']) and third['prompt'] != first['prompt']
    assert demo.pending is None and third['by'] == 'memory' and third['approved'] is True
    assert third['learned_from'] == [first['topic'], second['topic']]
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
    assert [row[4] for row in history_rows(demo)] == ['you', 'you', '⚡ learning (not asked)', 'you',
                                                       '⚡ learning (not asked)']


def test_a_model_allow_is_not_asked_or_learned():
    demo = LearningDemo(FakeScanner())   # answers ALLOW
    entry = demo.run(demo.next_case('get_file_by_id'))
    assert entry['by'] == 'laya' and entry['approved'] and demo.pending is None
    assert demo.status('get_file_by_id') == (0, 0, 'learning')


def test_the_learning_tab_runs_on_the_page():
    app = build_app(lambda *a, **k: None, scanner=ASKING)
    fns = {f.fn.__name__: f.fn for f in app.fns.values() if getattr(f.fn, '__name__', None)}
    assert [b for b in app.blocks.values() if getattr(b, 'label', None) == 'Kind of request']
    for _ in range(2):   # asked twice, approved
        demo, progress, card, rows, approve, reject, run_next, run_one = fns['learn_next_run'](
            None if _ == 0 else demo, 'get_file_by_id')
        assert demo.pending is not None and approve['interactive'] and not run_next['interactive']
        demo.answer(True)
    demo, progress, card, rows, approve, reject, run_next, run_one = fns['learn_next_run'](demo, 'get_file_by_id')
    assert demo.pending is None and not approve['interactive'] and run_next['interactive']
    assert 'Approved by learning' in card and len(rows) == 3
    picked = group_cases()['get_file_by_id'][-1]
    demo, *_ = fns['learn_case_run'](demo, picked)
    assert demo.history[-1]['id'] == picked and demo.history[-1]['by'] == 'memory'
