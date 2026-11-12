"""Shared test doubles: a fake laya-cybersec scanner and a scripted chat model's replies."""
import json

import grids_plugin  # noqa: F401  (puts the repository's src on the path)
from grids.actors.client.scripted import ScriptedActor
from grids_plugin.session import ATTACKER, COLLEAGUE, DemoSession  # noqa: F401


PROBABILITIES = {'ALLOW': {'ALLOW': 0.8, 'ASK': 0.1, 'BLOCK': 0.1}, 'ASK': {'ALLOW': 0.2, 'ASK': 0.6, 'BLOCK': 0.2},
                 'BLOCK': {'ALLOW': 0.1, 'ASK': 0.1, 'BLOCK': 0.8}}


class FakeScanner:
    """Stands in for laya-cybersec's rotated ALLOW / ASK / BLOCK. It reads the real compact_v1 reduction of the state.

    BLOCK when the injected instruction is in what the model reads; ASK for tools in `ask_tools`; otherwise ALLOW.
    """
    device = 'cpu'

    def __init__(self, ask_tools=()):
        self.contents, self.ask_tools = [], set(ask_tools)

    def decide(self, state, profile='compact_v1'):
        from grids.gatekeeper.context import compact
        content = compact(state)[0] if profile == 'compact_v1' else state
        self.contents.append(content)
        tool = json.loads(content)['untrusted_proposed_action']['tool']
        decision = ('BLOCK' if 'please do the following first' in content else
                    'ASK' if tool in self.ask_tools else 'ALLOW')
        return {'decision': decision, 'probabilities': PROBABILITIES[decision], 'answers': {}, 'error': None,
                'error_kind': None, 'tie': False, 'state_tokens': 300, 'sequence_tokens': 400, 'seconds': 0.001}


def call(name, **args):
    return {'role': 'assistant', 'content': None,
            'tool_calls': [{'id': f'call_{name}', 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}]}


def answer(text='Done.'):
    return {'role': 'assistant', 'content': text}


def email(to):
    return call('send_email', recipients=[to], subject='Code', body='The code is 463820')


def session(mode, scenario, replies, scanner=None, **kwargs):
    return DemoSession(mode, scenario, scanner, actor=ScriptedActor(replies), **kwargs)
