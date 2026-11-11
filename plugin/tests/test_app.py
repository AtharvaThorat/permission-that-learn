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


def factory(replies):
    def make_session(mode, scenario, compare):
        return DemoSession(mode, scenario, FakeScanner(), actor=ScriptedActor(list(replies)))
    return make_session


def handlers(app):
    return {fn.fn.__name__: fn.fn for fn in app.fns.values() if getattr(fn.fn, '__name__', '') in ('start', 'send')}


def test_send_streams_decisions_and_compute():
    app = build_app(factory([call('get_day_calendar_events', day='2024-05-15'), email(COLLEAGUE), answer('Two meetings.')]))
    fns = handlers(app)
    session, chat, prompt, info, *_ = fns['start']('Wall + laya-cybersec', 'Attack only laya-cybersec catches', False)
    assert 'Workspace reset' in info and prompt.startswith('How many appointments')
    *_, last = list(fns['send'](session, chat, prompt, 'Wall + laya-cybersec', 'Attack only laya-cybersec catches', False))
    session, chat, _, table, compute, *_ = last
    assert chat[-1] == {'role': 'assistant', 'content': 'Two meetings.'}
    assert [row[5] for row in table] == ['ALLOW', 'BLOCK'] and [row[6] for row in table] == ['yes', 'no']
    assert 'laya-cybersec' in compute and '| 2 |' in compute


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
