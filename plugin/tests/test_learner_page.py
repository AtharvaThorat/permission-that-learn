"""The demo page's permission memory is Atharva's learner (learner.py, the team's CountingMemory): 3 "Approve and
remember" answers of one kind, then a new request of that kind is approved without asking. Fake laya-cybersec that
answers ASK."""
import time

from support import FakeScanner

from grids_plugin.app import build_app, memory_markdown
from grids_plugin.learner import APPROVED, STOPPED, Learner
from grids_plugin.learning_demo import group_cases
from grids_plugin.memory import MODES as MEMORY_MODES
from grids_plugin.session import ASK_SCENARIOS, VERIFIED_CASES, DemoSession, ask_case, verified_case

ASKING = FakeScanner(ask_tools={s['tool'] for s in ASK_SCENARIOS.values()}
                     | {c['proposed_tool_call']['tool'] for c in VERIFIED_CASES.values()})
EMAILS = group_cases()['search_emails']


def run(learner, name, approve=True, remember=True):
    """One run of a case on the page; the simulated person answers if asked. Returns (asked, row)."""
    row = verified_case(name) if name in VERIFIED_CASES else ask_case(name)
    session = DemoSession('wall_laya', 'Free chat', ASKING, memory_mode='learner', learner=learner, row=row)
    thread, asked, deadline = session.start(row['prompt'], recorded=True), False, time.monotonic() + 60
    while thread.is_alive() and time.monotonic() < deadline:
        if session.pending:
            assert session.pending.get('key'), session.pending   # the kind this ask belongs to
            session.respond(approve, remember=remember and approve)
            asked = True
        time.sleep(0.05)
    thread.join(60)
    assert session.error is None, session.error
    return asked, list(session.rows.values())[-1], session


def test_three_remembered_approvals_then_a_new_request_of_that_kind_is_not_asked():
    learner = Learner()
    for name in EMAILS[:3]:
        asked, row, _ = run(learner, name)
        assert asked and row['executed'] and row['memory'] == 'approved and remembered'
    asked, row, session = run(learner, EMAILS[3])   # a different email search
    assert not asked and row['executed'] and row['memory'] == APPROVED
    assert session.row_result['asked'] is False
    # Other kinds learned nothing: a calendar lookup still asks.
    asked, _, _ = run(learner, group_cases()['search_calendar_events'][0])
    assert asked
    page = memory_markdown(session)
    assert '3 of 3' in page and '⚡ approves new ones' in page and 'search_emails' in page


def test_plain_approve_teaches_nothing_and_reject_stops_the_kind():
    learner = Learner()
    for name in EMAILS[:3]:
        asked, row, _ = run(learner, name, remember=False)
        assert asked and row['executed'] and row['memory'] == 'asked'
    asked, _, _ = run(learner, EMAILS[3])   # still asks: plain Approve does not count
    assert asked
    asked, row, _ = run(learner, EMAILS[4], approve=False)
    assert asked and not row['executed']
    asked, row, _ = run(learner, EMAILS[5])   # the kind is stopped without asking
    assert not asked and not row['executed'] and row['memory'] == STOPPED
    learner.forget()
    asked, _, _ = run(learner, EMAILS[6])
    assert asked


def test_a_live_action_through_the_controller_learns_by_kind():
    learner = Learner()
    name = next(iter(ASK_SCENARIOS))   # a Workspace request through the Wall, laya-cybersec and the approval channel
    for _ in range(3):
        asked, row, _ = run(learner, name)
        assert asked and row['executed'] and row['memory'] == 'approved and remembered'
    asked, row, _ = run(learner, name)
    assert not asked and row['executed'] and row['memory'] == APPROVED


def test_the_page_uses_only_atharvas_learner():
    learner = Learner()
    app = build_app(lambda *a, **k: None, learner=learner)
    radios = [b for b in app.blocks.values() if getattr(b, 'label', None) == 'Permission memory']
    assert radios and [c[0] for c in radios[0].choices] == [MEMORY_MODES['learner']] and not radios[0].visible
    buttons = [b.value for b in app.blocks.values() if type(b).__name__ == 'Button']
    assert '↺  Forget what the learner learned' in buttons
