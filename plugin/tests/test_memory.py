"""Permission memory: the repository's PermissionStore and ScopedApprovalProvider through the real controller.

The fake laya-cybersec answers ASK for send_email, so each send is one of the model's own asks that a grant may answer.
"""
import json
import threading
import time

import anyio
import pytest
from mcp.client import Client

from support import COLLEAGUE, FakeScanner, answer, call, session
from grids_plugin.mcp_server import GuardedWorkspace, build_server
from grids_plugin.memory import Memory

DAVID = 'david.smith@bluesparrowtech.com'
REQUEST = 'Email David hello.'


def send_to(to=DAVID):
    return call('send_email', recipients=[to], subject='Hi', body='Hello')


def run_with_answer(demo, prompt, approved=True, remember=False):
    """Run one message; if it waits for the person, answer it. Returns whether anyone was asked."""
    thread = threading.Thread(target=demo.run, args=(prompt,))
    thread.start()
    asked = False
    while thread.is_alive():
        if demo.pending:
            asked = True
            demo.respond(approved, remember=remember)
        time.sleep(0.02)
    thread.join()
    return asked


def demo_with(memory, mode='grants', scanner=None, replies=None, scenario='Free chat'):
    return session('wall_laya', scenario, replies or [send_to(), answer()], scanner or FakeScanner(ask_tools={'send_email'}),
                   memory=memory, memory_mode=mode, approval_wait=10)


@pytest.fixture
def memory(tmp_path):
    return Memory(tmp_path / 'permissions.sqlite')


def test_remembered_permission_answers_the_same_ask_after_a_reset(memory):
    first = demo_with(memory)
    assert run_with_answer(first, REQUEST, remember=True)
    (row,) = first.rows.values()
    assert (row['reason'], row['memory'], row['executed']) == ('NEEDS_CLARIFICATION', 'approved and remembered', True)
    (grant,) = memory.grants()
    assert (grant['tool'], grant['target'], grant['request'], grant['active']) == ('send_email', [DAVID], REQUEST, True)

    second = demo_with(memory)   # a fresh Workspace, the same store
    assert not run_with_answer(second, REQUEST), 'nobody is asked'
    (row,) = second.rows.values()
    assert (row['decision'], row['memory'], row['executed']) == ('ASK', 'answered by remembered permission', True)
    assert second.memory_summary() == {'mode': 'grants', 'eligible_asks': 1, 'answered_by_grant': 1, 'asked_person': 0,
                                       'learner_would_reuse': 0}
    assert memory.grants()[0]['uses'] == 1


def test_a_permission_is_exact(memory):
    assert run_with_answer(demo_with(memory), REQUEST, remember=True)
    other_target = demo_with(memory, replies=[send_to(COLLEAGUE), answer()])
    assert run_with_answer(other_target, REQUEST), 'another recipient is asked again'
    other_request = demo_with(memory)
    assert run_with_answer(other_request, 'Email David hello, please.'), 'another request is asked again'


def test_revoked_or_rejected_permissions_stop_answering(memory):
    assert run_with_answer(demo_with(memory), REQUEST, remember=True)
    memory.revoke(memory.grants()[0]['id'])
    assert run_with_answer(demo_with(memory), REQUEST, remember=True), 'revoked: asked again'
    assert run_with_answer(demo_with(memory, mode='shadow'), REQUEST, approved=False), 'shadow mode always asks'
    assert not any(g['active'] for g in memory.grants()), 'a rejection revokes the matching permission'


def test_shadow_mode_asks_even_with_a_permission(memory):
    assert run_with_answer(demo_with(memory), REQUEST, remember=True)
    shadow = demo_with(memory, mode='shadow')
    assert run_with_answer(shadow, REQUEST)
    assert shadow.memory_summary()['answered_by_grant'] == 0 and shadow.memory_summary()['eligible_asks'] == 1


def test_file_share_confirmation_can_never_be_remembered(memory):
    demo = demo_with(memory, scanner=FakeScanner(), scenario='Sharing needs your approval',
                     replies=[call('share_file', file_id='0', email=DAVID, permission='r'), answer()])
    thread = threading.Thread(target=demo.run, args=('Share the file with David.',))
    thread.start()
    while not demo.pending:
        time.sleep(0.02)
    assert demo.pending['rememberable'] is False
    with pytest.raises(ValueError):
        demo.respond(True, remember=True)
    demo.respond(True)
    thread.join()
    assert memory.grants() == []


def test_memory_needs_the_gatekeeper(memory):
    demo = session('wall_only', 'Free chat', [send_to(), answer()], memory=memory, memory_mode='grants')
    assert demo.memory is None and demo.memory_mode == 'off'


def test_mcp_server_reuses_a_permission_remembered_in_the_approval_console(tmp_path, memory):
    space = GuardedWorkspace(FakeScanner(ask_tools={'send_email'}), memory=memory, approvals=tmp_path / 'approvals',
                             approval_wait=10)

    def console_remembers():   # what typing `r` in the approval console does
        from grids.core.permissions.approvals import respond
        for _ in range(400):
            pending = [p for p in (tmp_path / 'approvals').glob('*.json') if not p.name.endswith('.response.json')]
            if pending:
                memory.remember(pending[0])
                respond(pending[0], True)
                return
            time.sleep(0.025)

    send = {'recipients': [DAVID], 'subject': 'Hi', 'body': 'Hello'}

    async def go():
        async with Client(build_server(space)) as client:
            await client.call_tool('set_user_request', {'request': REQUEST})
            first = await client.call_tool('send_email', send)
            await client.call_tool('set_user_request', {'request': REQUEST})
            again = await client.call_tool('send_email', send)
            report = await client.call_tool('guard_report', {})
            return first, again, json.loads(report.content[0].text)

    threading.Thread(target=console_remembers, daemon=True).start()
    first, again, report = anyio.run(go)
    assert not first.is_error and not again.is_error
    assert [(d['memory'], d['person']) for d in report['decisions']] == [
        ('asked', 'approved'), ('answered by remembered permission', 'not asked: remembered permission')]
    assert report['memory']['answered_by_grant'] == 1 and len(report['memory']['grants']) == 1
