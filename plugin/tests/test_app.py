"""The chat page's handlers, driven directly with a scripted chat model and the fake scanner."""
import socket
import threading
import time
import urllib.request

import grids_plugin  # noqa: F401
from grids.actors.client.scripted import ScriptedActor
from grids_plugin.app import build_app, compute_markdown
from grids_plugin.session import COLLEAGUE, DemoSession
from support import FakeScanner, answer, call, email


def factory(replies, memory=None, scanner=None):
    def make_session(mode, scenario, compare, memory_mode):
        return DemoSession(mode, scenario, scanner or FakeScanner(), memory=memory, memory_mode=memory_mode,
                           actor=ScriptedActor(list(replies)))
    return make_session


def handlers(app):
    return {fn.fn.__name__: fn.fn for fn in app.fns.values() if getattr(fn.fn, '__name__', '') in ('start', 'send')}


def test_send_streams_decisions_and_compute():
    app = build_app(factory([call('get_day_calendar_events', day='2024-05-15'), email(COLLEAGUE), answer('Two meetings.')]))
    fns = handlers(app)
    args = ('Wall + laya-cybersec', 'Attack only laya-cybersec catches', False, 'Off (always ask)')
    session, chat, prompt, info, *_ = fns['start'](*args)
    assert 'Workspace reset' in info and prompt.startswith('How many appointments')
    *_, last = list(fns['send'](session, chat, prompt, *args))
    session, chat, _, table, compute, *_ = last
    assert chat[-1] == {'role': 'assistant', 'content': 'Two meetings.'}
    assert [row[5] for row in table] == ['ALLOW', 'BLOCK'] and [row[7] for row in table] == ['yes', 'no']
    assert table[1][4] == 'ALLOW 0.10 · ASK 0.10 · BLOCK 0.80'
    assert 'laya-cybersec' in compute and '| 2 |' in compute


def test_approve_and_remember_from_the_page(tmp_path):
    from grids_plugin.memory import Memory
    memory = Memory(tmp_path / 'permissions.sqlite')
    reply = [call('send_email', recipients=['david.smith@bluesparrowtech.com'], subject='Hi', body='Hello'), answer('Sent.')]
    app = build_app(factory(reply, memory, FakeScanner(ask_tools={'send_email'})), memory=memory)
    fns = handlers(app)
    args = ('Wall + laya-cybersec', 'Free chat', False, 'Grants (reuse remembered permissions)')
    request = 'Email David hello.'
    session, chat, *_ = fns['start'](*args)
    stream = fns['send'](session, chat, request, *args)
    for update in stream:
        if update[5]:   # the page shows the ask; the person presses "Approve and remember"
            assert update[7]['interactive'] is True and 'approve and remember' in update[5], (update[5], update[6], update[7])
            update[0].respond(True, remember=True)
            break
    *_, last = list(stream)
    assert last[3][0][6] == 'approved and remembered' and last[3][0][7] == 'yes'
    assert [g[1] for g in last[-2]] == ['send_email']
    session, chat, *_ = fns['start'](*args)   # Workspace reset; the permission is kept
    *_, last = list(fns['send'](session, chat, request, *args))
    assert last[3][0][6] == 'answered by remembered permission' and last[3][0][7] == 'yes'
    assert 'answered by a remembered permission' in last[9] and '**1** answered' in last[9]


def test_compute_text_states_the_comparison():
    text = compute_markdown({'agent_calls': 3, 'agent_tokens': 1200, 'agent_seconds': 2.0, 'wall_checks': 3, 'wall_stopped': 1,
                             'wall_seconds': 0.001, 'laya_scans': 1, 'laya_seconds': 0.4, 'laya_parameters': 1, 'laya_device': 'cpu',
                             'model_checks_avoided': 1, 'judge_calls': 1, 'judge_tokens': 700, 'judge_seconds': 1.5}, True)
    assert '**1** action(s) stopped by the Wall alone' in text and 'chat model as judge took **1.50 s**' in text


def test_page_serves():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    app = build_app(factory([answer()]))
    thread = threading.Thread(target=lambda: app.queue().launch(server_port=port, prevent_thread_lock=True), daemon=True)
    thread.start()
    for _ in range(100):
        try:
            assert urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=2).status == 200
            break
        except OSError:
            time.sleep(0.2)
    else:
        raise AssertionError('the page did not start')
    app.close()
