"""ASK scenarios: the page's Load / Run buttons and the full memory loop (fake laya-cybersec that answers ASK).
The real model's answers on these scenarios are checked by `python -m grids_plugin.ask_check`."""
from support import FakeScanner

from grids_plugin.app import build_app
from grids_plugin.ask_check import scenario_loop
from grids_plugin.memory import Memory
from grids_plugin.session import ASK_SCENARIOS, VERIFIED_CASES, DemoSession, ask_case, verified_case

ASKING = FakeScanner(ask_tools={s['tool'] for s in ASK_SCENARIOS.values()}
                     | {c['proposed_tool_call']['tool'] for c in VERIFIED_CASES.values()})


def test_siddharths_verified_cases_are_on_the_page():
    from collections import Counter
    assert len(VERIFIED_CASES) == 52
    assert {'REAL-ASK-WORKSPACE-001', 'REAL-ASK-SLACK-001', 'REAL-ASK-BANKING-001', 'WS-ASK-EMAIL-001'} <= set(VERIFIED_CASES)
    assert Counter(c['category'] for c in VERIFIED_CASES.values()) == {'email': 19, 'files': 16, 'calendar': 15,
                                                                         'slack': 1, 'banking': 1}
    for case in VERIFIED_CASES.values():   # one shape: a tool name and an exact permission scope for every case
        assert case['proposed_tool_call']['tool'] == case['scope']['tool']
        assert set(case['scope']) == {'request', 'tool', 'arguments', 'facts', 'policy_version', 'schema_digest'}


def test_borderline_cases_are_labelled_from_the_recorded_plugin_check():
    from grids_plugin.app import QUICK
    from grids_plugin.session import PLUGIN_RESULTS, borderline, case_label
    assert set(PLUGIN_RESULTS) == set(VERIFIED_CASES)   # ask_check --record covered every case
    flagged = sorted(name for name in VERIFIED_CASES if borderline(name))
    assert flagged == ['WS-ASK-CALENDAR-011', 'WS-ASK-EMAIL-004', 'WS-ASK-EMAIL-005', 'WS-ASK-EMAIL-007',
                       'WS-ASK-EMAIL-009', 'WS-ASK-EMAIL-011', 'WS-ASK-FILES-011']
    assert 'borderline' in case_label(VERIFIED_CASES['WS-ASK-EMAIL-004'])
    assert 'borderline' not in case_label(VERIFIED_CASES['WS-ASK-EMAIL-001'])
    app = build_app(lambda *a, **k: None)
    quick = [b.value for b in app.blocks.values() if type(b).__name__ == 'Button' and b.value in dict(QUICK).values()]
    assert len(quick) == 3   # one quick start per category, each a case the plugin's method asks on


def test_a_new_format_case_is_checked_against_its_recorded_binding():
    import copy
    import json
    import pytest
    from grids_plugin.session import VERIFIED_FILES, normalize_case
    raw = json.loads(VERIFIED_FILES[1].read_text(encoding='utf-8'))['cases'][0]
    case = normalize_case(raw)
    assert case['scope']['schema_digest'] == raw['controller_events'][0]['schema_digest']
    assert case['scope']['request'] == raw['user_prompt'] and case['scope']['facts'] == \
        raw['gatekeeper_input']['verified_context']['facts']['metadata']
    changed = copy.deepcopy(raw)
    changed['proposed_tool_call']['arguments']['query'] = 'something else'
    with pytest.raises(ValueError, match='recorded binding'):
        normalize_case(changed)


def test_every_scenario_asks_remembers_reuses_and_revokes(tmp_path):
    memory = Memory(tmp_path / 'permissions.sqlite')
    for name in list(VERIFIED_CASES) + list(ASK_SCENARIOS):
        loop = scenario_loop(name, ASKING, memory)
        assert loop['passed'], loop


def test_load_and_run_a_scenario_on_the_page(tmp_path):
    memory = Memory(tmp_path / 'permissions.sqlite')

    def make_session(mode, scenario, compare, memory_mode, row=None):
        return DemoSession(mode, scenario, ASKING, memory=memory, memory_mode=memory_mode, row=row)

    app = build_app(make_session, memory=memory)
    run = next(fn.fn for fn in app.fns.values() if getattr(fn.fn, '__name__', '') == 'run_item')
    name = 'Email that waits for your confirmation'
    # One Run: (state, chat, prompt, info, table, compute, pending, approve, remember, reject, memory, grants, revoke)
    args = (f'case:{name}', 'Wall + laya-cybersec', False, 'Grants (reuse remembered permissions)')
    stream = run(*args)
    first = next(stream)
    assert first[2] == ASK_SCENARIOS[name]['prompt'] and 'ASK case' in first[3]
    for update in stream:
        if update[6]:   # waiting for the person: Approve and remember is offered
            assert update[8]['interactive'] is True
            update[0].respond(True, remember=True)
            break
    *_, last = list(stream)
    result = last[1][-1]
    assert result['metadata']['title'].startswith('Result of the action')
    assert '**laya-cybersec:** ASK' in result['content'] and '**approved** it and remembered it' in result['content']
    *_, last = list(run(*args))   # the same item again: a fresh Workspace, answered by the remembered permission
    assert 'you were **not asked**' in last[1][-1]['content'] and last[4][0][7] == 'yes'


def test_pipeline_without_the_wall(tmp_path):
    from test_rows import GOAL, dataset_rows
    memory = Memory(tmp_path / 'permissions.sqlite')

    def make_session(mode, scenario, compare, memory_mode, row=None):
        return DemoSession(mode, scenario, FakeScanner(), memory=memory, memory_mode=memory_mode, row=row)

    app = build_app(make_session, memory=memory, rows=dataset_rows())
    run = next(fn.fn for fn in app.fns.values() if getattr(fn.fn, '__name__', '') == 'run_item')
    learning = 'Active (learner decides when to reuse)'
    # The attack row: with the Wall it is stopped there; without it, laya-cybersec sees the injection and blocks it.
    *_, with_wall = list(run(f'row:{GOAL}', 'Wall + laya-cybersec', False, learning))
    *_, no_wall = list(run(f'row:{GOAL}', 'laya-cybersec (no Wall)', False, learning))
    assert with_wall[4][0][3] == 'DENY' and with_wall[4][0][4] == '-'
    assert no_wall[4][0][3] == 'off' and no_wall[4][0][5] == 'BLOCK' and no_wall[4][0][7] == 'no'
    assert '**Wall:** off in this pipeline.' in no_wall[1][-1]['content'] and 'no Wall' in no_wall[3]


def test_one_list_holds_the_cases_and_the_dataset_rows():
    from test_rows import dataset_rows
    rows = dataset_rows()
    app = build_app(lambda *a, **k: None, rows=rows)
    choices = next(b for b in app.blocks.values() if getattr(b, 'label', None) == 'Action to test').choices
    values = [value for _, value in choices]
    cases = len(VERIFIED_CASES)
    assert values[:cases] == [f'case:{name}' for name in VERIFIED_CASES]   # only the verified ASK cases
    # dataset rows reviewed as ALLOW or BLOCK only (GRIDS_306 is reviewed ASK)
    assert {i: r['reviewed_label'] for i, r in rows.rows.items()} == {'GRIDS_305': 'BLOCK', 'GRIDS_306': 'ASK'}
    assert values[cases:] == ['row:GRIDS_305']
    # the category filter offers the same items in groups
    groups = next(b for b in app.blocks.values() if type(b).__name__ == 'Radio' and str(b.value).startswith('All')).choices
    assert [label for label, _ in groups] == [f'All ({cases + 1})', 'Email (19)', 'Calendar (15)', 'Files (16)',
                                              'Slack & Banking (2)', 'Team dataset rows (1)']


def test_new_cases_run_on_the_page_and_the_pipeline_view_follows(tmp_path):
    memory = Memory(tmp_path / 'permissions.sqlite')

    def make_session(mode, scenario, compare, memory_mode, row=None):
        return DemoSession(mode, scenario, ASKING, memory=memory, memory_mode=memory_mode, row=row)

    app = build_app(make_session, memory=memory)
    run = next(fn.fn for fn in app.fns.values() if getattr(fn.fn, '__name__', '') == 'run_item')
    args = ('case:WS-ASK-CALENDAR-001', 'Wall + laya-cybersec', False, 'Grants (reuse remembered permissions)')
    stream = run(*args)
    for update in stream:
        if update[6]:   # the guard asks: the pipeline view says so, then the person rejects
            assert 'Waiting for your decision' in update[-1] and '? Waiting for you' in update[-1]
            update[0].respond(False)
            break
    *_, last = list(stream)
    assert 'You rejected it' in last[-1] and 'Stopped by you' in last[-1] and last[4][0][7] == 'no'


def test_remembering_the_same_ask_twice_keeps_one_permission(tmp_path):
    """In Shadow the same ask comes back; a second Approve and remember reuses the grant instead of adding one."""
    import time
    from grids_plugin.app import pending_markdown
    memory = Memory(tmp_path / 'permissions.sqlite')
    for name in (next(iter(VERIFIED_CASES)), next(iter(ASK_SCENARIOS))):   # a verified case and a live scenario
        seen = []
        for _ in range(3):
            row = verified_case(name) if name in VERIFIED_CASES else ask_case(name)
            session = DemoSession('wall_laya', 'Free chat', ASKING, memory=memory, memory_mode='shadow', row=row)
            thread = session.start(row['prompt'], recorded=True)
            deadline = time.monotonic() + 60
            while thread.is_alive() and time.monotonic() < deadline:
                waiting = session.pending
                if waiting:
                    seen.append(waiting.get('remembered'))
                    note = pending_markdown(session, waiting)
                    session.respond(True, remember=True)
                time.sleep(0.05)
            thread.join(60)
        assert seen[0] is None and seen[1] and seen[1] == seen[2], seen   # asked each time; remembered once
        assert 'Already remembered' in note
    assert len(memory.grants()) == 2, memory.grants()   # one per scope, not one per click
