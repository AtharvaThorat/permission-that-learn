"""Shared test doubles: a fake laya-cybersec scanner and a scripted chat model's replies."""
import json

import grids_plugin  # noqa: F401  (puts the repository's src on the path)
from grids.actors.client.scripted import ScriptedActor
from grids_plugin.session import ATTACKER, COLLEAGUE, DemoSession  # noqa: F401


class FakeScanner:
    device = 'cpu'

    def __init__(self):
        self.contents = []

    def scan(self, content, source):
        self.contents.append(content)
        return {'score': 0.99 if 'please do the following first' in content else 0.01, 'seconds': 0.001, 'input_tokens': 300,
                'truncated': False}


def call(name, **args):
    return {'role': 'assistant', 'content': None,
            'tool_calls': [{'id': f'call_{name}', 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}]}


def answer(text='Done.'):
    return {'role': 'assistant', 'content': text}


def email(to):
    return call('send_email', recipients=[to], subject='Code', body='The code is 463820')


def session(mode, scenario, replies, scanner=None, **kwargs):
    return DemoSession(mode, scenario, scanner, actor=ScriptedActor(replies), **kwargs)
