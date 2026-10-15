import json
from types import SimpleNamespace
from pydantic import BaseModel
from blackbox.actors.scripted import ScriptedActor
from blackbox.audit import MemoryAudit
from blackbox.config import Config
from blackbox.contracts import Dependencies, GateDecision
from blackbox.factory import build_agentdojo_pipeline
from blackbox.permissions.wall import Policy, ReferenceWall

class Clock:
    def __init__(self):
        self.now = 100.0
    def monotonic(self):
        return self.now

class Read(BaseModel):
    file_id: str

class Send(BaseModel):
    recipients: list[str]
    subject: str
    body: str
    attachments: list[dict] | None = None
    cc: list[str] | None = None
    bcc: list[str] | None = None

class CountingRuntime:
    def __init__(self):
        self.calls = []
        self.error_after_mutation = False
        self.on_dispatch = None
        self.functions = {name: SimpleNamespace(name=name, description='Synthetic tool', parameters=schema)
                          for name, schema in [('get_file_by_id', Read), ('delete_file', Read), ('send_email', Send)]}
    def run_function(self, env, name, args):
        self.calls.append((name, args.copy()))
        env['mutations'] += 1
        if self.on_dispatch:
            self.on_dispatch(env)
        if self.error_after_mutation:
            return '', 'SyntheticError: state changed before failure'
        return env.get('tool_text', 'Meeting notes: launch on Friday.'), None

class Facts:
    def __init__(self):
        self.observed, self.missing = [], False
    def resolve(self, tool, args, env):
        self.observed.append(env['version'])
        return {'source': 'synthetic_metadata', 'version': env['version'],
                'recipients': args.get('recipients', []), 'resources': [],
                'missing': ['resource_identity'] if self.missing else []}

class Gate:
    def __init__(self, labels=('ALLOW',)):
        self.labels, self.calls, self.closed, self.hook = iter(labels), [], False, None
    def evaluate(self, episode, action, wall):
        self.calls.append((episode.task, action))
        if self.hook:
            self.hook()
        label = next(self.labels, 'ALLOW')
        if isinstance(label, Exception):
            raise label
        return GateDecision(label, 'SCRIPTED_TEST', backend='scripted_test') if isinstance(label, str) else label
    def close(self):
        self.closed = True

def call(name='get_file_by_id', args=None, id='call_1'):
    return {'type': 'function', 'id': id, 'function': {'name': name,
            'arguments': json.dumps(args if args is not None else {'file_id': 'notes-7'})}}

def reply(*calls, content=None):
    return {'role': 'assistant', 'content': content, 'tool_calls': list(calls)}

def fixture(replies=None, labels=('ALLOW',), *, mode='wall_gatekeeper', approvals=None, audit=None, config=None):
    actor = ScriptedActor(replies if replies is not None else [reply(call()), reply(content='Summary complete.')])
    gate, facts, clock = Gate(labels), Facts(), Clock()
    wall = ReferenceWall(Policy(policy_id='test-reference', version='1',
        allowed_effects=['read', 'outbound', 'file_write'], approved_addresses=['known@example.com']))
    deps = Dependencies(actor=actor, gatekeeper=gate, wall=wall, facts=facts, clock=clock,
                        audit=audit if audit is not None else MemoryAudit(), approvals=approvals, run_id='test')
    pipeline = build_agentdojo_pipeline(config or Config(mode=mode), deps)
    return SimpleNamespace(pipeline=pipeline, runtime=CountingRuntime(), env={'mutations': 0, 'version': 1},
        actor=actor, gate=gate, facts=facts, wall=wall, clock=clock, audit=deps.audit)

def run(f, task='Read meeting notes and summarize.', messages=None, extra=None):
    return f.pipeline.query(task, f.runtime, f.env, messages, extra)
