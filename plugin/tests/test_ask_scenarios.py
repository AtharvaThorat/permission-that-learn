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
    fns = {fn.fn.__name__: fn.fn for fn in app.fns.values() if getattr(fn.fn, '__name__', '') in ('load_case', 'run_row')}
    name = 'Email that waits for your confirmation'
    args = (name, 'Wall + laya-cybersec', False, 'Grants (reuse remembered permissions)')
    session, chat, prompt, info, *_, run_button = fns['load_case'](*args)
    assert prompt == ASK_SCENARIOS[name]['prompt'] and 'ASK scenario' in info and run_button['interactive'] is True
    stream = fns['run_row'](session, chat)
    for update in stream:
        if update[4]:   # waiting for the person: Approve and remember is offered
            assert update[6]['interactive'] is True
            update[0].respond(True, remember=True)
            break
    *_, last = list(stream)
    assert 'decision **ASK**' in last[1][-1]['content'] and 'approved and remembered' in last[1][-1]['content']
    session, chat, *_ = fns['load_case'](*args)
    *_, last = list(fns['run_row'](session, chat))
    assert 'answered by remembered permission' in last[1][-1]['content'] and last[2][0][7] == 'yes'
