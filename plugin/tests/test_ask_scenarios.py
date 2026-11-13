"""ASK scenarios: the page's Load / Run buttons and the full memory loop (fake laya-cybersec that answers ASK).
The real model's answers on these scenarios are checked by `python -m grids_plugin.ask_check`."""
from support import FakeScanner

from grids_plugin.app import build_app
from grids_plugin.ask_check import scenario_loop
from grids_plugin.memory import Memory
from grids_plugin.session import ASK_SCENARIOS, VERIFIED_CASES, DemoSession

ASKING = FakeScanner(ask_tools={s['tool'] for s in ASK_SCENARIOS.values()}
                     | {c['proposed_tool_call']['tool'] for c in VERIFIED_CASES.values()})


def test_siddharths_verified_cases_are_on_the_page():
    assert len(VERIFIED_CASES) == 3
    assert {c['id'] for c in VERIFIED_CASES.values()} == {'REAL-ASK-WORKSPACE-001', 'REAL-ASK-SLACK-001', 'REAL-ASK-BANKING-001'}


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
    choices = next(b for b in app.blocks.values() if getattr(b, 'label', None) == 'Item').choices
    values = [value for _, value in choices]
    assert values[:3] == [f'case:{name}' for name in VERIFIED_CASES]   # only the verified ASK cases
    # dataset rows reviewed as ALLOW or BLOCK only (GRIDS_306 is reviewed ASK)
    assert {i: r['reviewed_label'] for i, r in rows.rows.items()} == {'GRIDS_305': 'BLOCK', 'GRIDS_306': 'ASK'}
    assert values[3:] == ['row:GRIDS_305']
