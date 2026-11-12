"""laya-cybersec in the Gatekeeper slot of the repository's controller, plus the compute ledger.

The controller is unchanged: it binds each proposed tool call, asks the Wall, and only on PASS calls the gate below.
The gate builds the same decision context as the laya-permission-v1 data (request, action, policy, trusted identities and
the untrusted tool history), reduces it with the repository's `compact_v1` (made for this model's 1,024 tokens) and asks
laya-cybersec for ALLOW, ASK or BLOCK with the team's rotated-option method (see `cybersec.py`).
"""
import json
import time
from grids.core.contracts import GateDecision
from grids.gatekeeper.context import compact
from .cybersec import METHOD, MODEL_ID, PARAMETERS, REVISION

# The repository Gatekeeper's reason codes (grids.gatekeeper.policy). Siddharth's scoped grants may answer only the
# model's own asks, NEEDS_CLARIFICATION and UNCERTAIN (grids.core.permissions.memory.ELIGIBLE_REASONS).
REASONS = {'ALLOW': 'TASK_AUTHORIZED', 'BLOCK': 'TASK_MISMATCH', 'ASK': 'NEEDS_CLARIFICATION'}


def plain(value):
    # Sets become sorted lists, so the same state always produces the same text.
    if isinstance(value, dict):
        return {key: plain(item) for key, item in sorted(value.items())}
    if isinstance(value, (set, frozenset)):
        return sorted(plain(item) for item in value)
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


def text_of(content):
    if isinstance(content, list):
        return '\n'.join(str(block.get('content') or block.get('text') or '') for block in content if isinstance(block, dict))
    return '' if content is None else str(content)


def decision_state(task, action, verdict, wall, history):
    """The full JSON state for one Wall-approved action; the gate reduces it with compact_v1 before the model reads it."""
    state = {'authentic_user_request': task,
             'untrusted_proposed_action': {'tool': action.tool, 'arguments': json.loads(action.arguments_json)},
             'verified_context': {'confirmation_required': verdict.confirmation_required,
                                  'evidence_complete': action.evidence_complete,
                                  'facts': {'metadata': json.loads(action.facts_json), 'effects': list(action.effects),
                                            'permission_policy': plain(wall.policy.model_dump(mode='json')),
                                            'trusted_identities': plain(wall.context.model_dump(mode='json')),
                                            'untrusted_history': [{'role': m.get('role'), 'content': text_of(m.get('content')),
                                                                   'tool_calls': m.get('tool_calls'), 'name': m.get('name')}
                                                                  for m in history if m.get('role') in ('assistant', 'tool')]}},
             'wall': {'verdict': verdict.verdict, 'policy_version': verdict.policy_version,
                      'evaluated_action_id': action.action_id, 'reason_codes': [verdict.reason]}}
    return json.dumps(state, ensure_ascii=False)


def decision_context(task, action, verdict, wall, history):
    """The compact_v1 text laya-cybersec reads for one Wall-approved action, and its diagnostics."""
    return compact(decision_state(task, action, verdict, wall, history))


class RecordingActor:
    """Wraps the chat model client: keeps the latest conversation for the gate and each call's cost for the ledger."""

    def __init__(self, actor):
        self.actor, self.messages, self.calls = actor, [], []

    def respond(self, messages, tools, timeout):
        self.messages = messages
        started = time.perf_counter()
        error = None
        try:
            return self.actor.respond(messages, tools, timeout)
        except Exception as exc:
            error = type(exc).__name__
            raise
        finally:
            usage = (getattr(self.actor, 'last_metadata', None) or {}).get('usage') or {}
            self.calls.append({'seconds': time.perf_counter() - started, 'error': error,
                               'prompt_tokens': usage.get('prompt_tokens'), 'completion_tokens': usage.get('completion_tokens')})

    def close(self):
        self.actor.close()


class TimedWall:
    """The repository's Wall, unchanged, with each check timed precisely (the controller's clock is too coarse)."""

    def __init__(self, wall):
        self.wall, self.checks = wall, []

    def evaluate(self, action):
        started = time.perf_counter()
        verdict = self.wall.evaluate(action)
        self.checks.append({'action_id': action.action_id, 'verdict': verdict.verdict,
                            'seconds': time.perf_counter() - started})
        return verdict

    def __getattr__(self, name):
        return getattr(self.wall, name)


class CybersecGate:
    """Gate protocol for the controller: laya-cybersec's rotated-option ALLOW / ASK / BLOCK on the action's context.

    ALLOW is TASK_AUTHORIZED, BLOCK is TASK_MISMATCH, ASK is NEEDS_CLARIFICATION, and a tie between labels is ASK
    UNCERTAIN, as in the repository's Gatekeeper policy. A failed or truncated answer is ASK with its error kind, which
    the controller turns into MODEL_UNAVAILABLE: a person decides, and no remembered grant may answer it.
    """

    def __init__(self, scanner, wall, history):
        self.scanner, self.wall, self.history = scanner, wall, history
        self.scans = []

    def set_native_schemas(self, runtime):
        pass   # the controller has already validated the arguments against the native schemas

    def evaluate(self, episode, action, verdict):
        state = decision_state(episode.task, action, verdict, self.wall, self.history())
        result = self.scanner.decide(state, profile='compact_v1')
        self.scans.append({'action_id': action.action_id, 'tool': action.tool, **result})
        common = dict(backend='laya_cybersec', prompt_version=METHOD, checkpoint=MODEL_ID, revision=REVISION,
                      probabilities=result['probabilities'], raw_recommendation=result['decision'],
                      calibration='uncalibrated; mean of three option orders',
                      diagnostics={'seconds': result['seconds'], 'state_tokens': result['state_tokens'],
                                   'sequence_tokens': result['sequence_tokens'],
                                   'evidence_excerpts': result.get('evidence_excerpts')})
        if result['error']:
            return GateDecision('ASK', 'MODEL_UNAVAILABLE', error_kind=result['error_kind'], **common)
        if result['tie']:
            return GateDecision('ASK', 'UNCERTAIN', **common)
        return GateDecision(result['decision'], REASONS[result['decision']], **common)

    def close(self):
        pass


def gate_output(probabilities):
    """laya-cybersec's averaged probabilities for the decisions table."""
    if not probabilities:
        return None
    return ' · '.join(f'{label} {probabilities[label]:.2f}' for label in ('ALLOW', 'ASK', 'BLOCK') if label in probabilities)


def ledger(wall_checks, actor_calls, scans, judge_calls=(), laya_device='cpu'):
    """Compute used so far: the chat model, the Wall, laya-cybersec, and the optional LLM-judge comparison."""
    stopped = sum(check['verdict'] != 'PASS' for check in wall_checks)
    tokens = [(c.get('prompt_tokens') or 0) + (c.get('completion_tokens') or 0) for c in actor_calls]
    judge_tokens = [(c.get('prompt_tokens') or 0) + (c.get('completion_tokens') or 0) for c in judge_calls]
    return {'agent_calls': len(actor_calls), 'agent_tokens': sum(tokens), 'agent_seconds': sum(c['seconds'] for c in actor_calls),
            'wall_checks': len(wall_checks), 'wall_stopped': stopped,
            'wall_seconds': sum(check['seconds'] for check in wall_checks),
            'laya_scans': len(scans), 'laya_seconds': sum(s['seconds'] for s in scans),
            'laya_parameters': PARAMETERS, 'laya_device': laya_device,
            'model_checks_avoided': stopped,
            'judge_calls': len(judge_calls), 'judge_tokens': sum(judge_tokens),
            'judge_seconds': sum(c['seconds'] for c in judge_calls)}
