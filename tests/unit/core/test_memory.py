"""Approval memory: scope, learners, controller boundaries, simulator invariants."""
import threading
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from grids.core.config import LearningConfig
from grids.core.contracts import GateDecision
from grids.core.permissions.approvals import ApprovalEvent, PendingApprovalProvider
from grids.core.permissions.memory import BanditMemory, CountingMemory, MemoryApprovalProvider, pattern_key
from grids.evaluation import memory_sim as sim
from grids.gatekeeper.rules import rules_decision
from .helpers import call, fixture, reply, run

ASK = GateDecision('ASK', 'NEEDS_CLARIFICATION')


def approve(p):
    return ApprovalEvent(p.pending_id, p.binding, True)


def reject(p):
    return ApprovalEvent(p.pending_id, p.binding, False)


class User:
    """Stands in for the person: answers in order and counts how often it was asked."""
    def __init__(self, answers):
        self.answers, self.calls = list(answers), 0

    def request(self, pending):
        self.calls += 1
        answer = self.answers.pop(0) if self.answers else None
        return answer(pending) if callable(answer) else answer


def provider(user, log, memory=None):
    return MemoryApprovalProvider(user, memory or CountingMemory(), classify=lambda v: 'contact', record=log.append)


def three_reads():
    return [reply(call(id='c1')), reply(call(id='c2')), reply(call(id='c3')), reply(content='Done.')]


def test_pattern_key_scope():
    one = {'recipients': ['a@example.com'], 'cc': None, 'subject': 'Hi'}
    other = {'recipients': ['b@example.com'], 'subject': 'Hi'}
    contact = lambda value: 'contact'
    assert pattern_key('send_email', one, contact, 'exact', 'p1') != pattern_key('send_email', other, contact, 'exact', 'p1')
    assert pattern_key('send_email', one, contact, 'class', 'p1') == pattern_key('send_email', other, contact, 'class', 'p1')
    assert pattern_key('append_to_file', {'file_id': '3'}, contact, 'exact', 'p1') != \
        pattern_key('append_to_file', {'file_id': '4'}, contact, 'exact', 'p1')
    assert pattern_key('send_email', one, contact, 'exact', 'p1') != pattern_key('send_email', one, contact, 'exact', 'p2')


def test_counting_allows_after_k_tightens_on_rejection_and_expires():
    m = CountingMemory(approvals_to_allow=2, ttl=3)
    assert m.decide('a') == 'ask'
    m.update('a', True)
    assert m.decide('a') == 'ask'
    m.update('a', True)
    assert m.decide('a') == 'allow' and m.allowed() == ['a']
    m.update('a', False)
    assert m.decide('a') == 'block' and m.allowed() == []
    for _ in range(4):
        m.decide('b')
    assert m.decide('a') == 'ask'  # unused past its ttl: forgotten


def test_bandit_is_seeded_never_blocks_and_needs_evidence():
    a, b = BanditMemory(seed=7), BanditMemory(seed=7)
    assert a.decide('k') == 'ask'
    for m in (a, b):
        for _ in range(30):
            m.update('k', True)
    choices = [a.decide('k') for _ in range(50)]
    assert choices == [b.decide('k') for _ in range(50)] and 'allow' in choices and 'block' not in choices


def test_memory_answers_a_repeated_ask_through_the_controller():
    user, log = User([approve, approve]), []
    f = fixture(three_reads(), labels=(ASK, ASK, ASK), approvals=provider(user, log))
    run(f)
    assert user.calls == 2 and len(f.runtime.calls) == 3
    assert [r['source'] for r in log] == ['user', 'user', 'memory']


def test_a_rejection_tightens_without_dispatch():
    user, log = User([reject]), []
    f = fixture(three_reads(), labels=(ASK, ASK, ASK), approvals=provider(user, log))
    run(f)
    # The controller's repeated-denial limit may end the episode before a third call.
    assert user.calls == 1 and not f.runtime.calls
    assert [(r['source'], r['approved']) for r in log][:2] == [('user', False), ('memory', False)]


def test_wall_denial_never_reaches_memory():
    user, log = User([approve]), []
    f = fixture([reply(call('delete_file')), reply(content='Cannot.')], labels=(ASK,), approvals=provider(user, log))
    run(f)
    assert user.calls == 0 and log == [] and not f.runtime.calls


@pytest.mark.parametrize('reason', ['MODEL_UNAVAILABLE', 'CONFIRMATION_REQUIRED', 'INSUFFICIENT_EVIDENCE'])
def test_forced_asks_always_reach_the_user_and_are_not_learned(reason):
    user, log = User([approve, approve, approve]), []
    ask = GateDecision('ASK', reason)
    f = fixture(three_reads(), labels=(ask, ask, ask), approvals=provider(user, log))
    run(f)
    assert user.calls == 3 and log == []


def test_only_answers_bound_to_the_pending_action_are_learned():
    memory, log = CountingMemory(approvals_to_allow=1), []
    forged = lambda p: ApprovalEvent('someone-else', p.binding, True)
    pending = SimpleNamespace(pending_id='p1', reason='NEEDS_CLARIFICATION', binding=SimpleNamespace(policy_version='v', action_id='a'),
                              action=SimpleNamespace(tool='send_email', arguments_json='{"recipients": ["a@example.com"]}'))
    MemoryApprovalProvider(User([forged]), memory, classify=str, record=log.append).request(pending)
    assert memory.records == {} and log == []


def test_rules_gatekeeper():
    assert rules_decision(('read',))[0] == 'ALLOW'
    assert rules_decision(('read', 'mark_read'))[0] == 'ALLOW'
    assert rules_decision(('destructive', 'outbound'))[0] == 'BLOCK'
    assert rules_decision(('outbound',))[0] == rules_decision(('financial', 'outbound'))[0] == 'ASK'
    assert rules_decision(('read', 'outbound'))[0] == 'ASK'


def test_learning_config_and_spec_identity():
    from grids.runs.spec import load
    with pytest.raises(ValidationError):
        LearningConfig(wrong_allow_cost=0.5)
    spec = load('configs/experiments/smoke.json')
    assert 'learning' not in spec.model_dump()  # disabled: existing run identities unchanged
    enabled = spec.model_copy(update={'learning': LearningConfig(enabled=True)})
    assert enabled.model_dump()['learning']['enabled'] is True




@pytest.fixture(scope='module')
def events():
    return sim.load_events()


def test_simulator_is_deterministic(events):
    banking = [e for e in events if e.suite == 'banking']
    for setup, learner, granularity in sim.LEARNING:
        first = sim.simulate_stream(banking, setup, learner, granularity, 0.2, 3, 2)
        assert first == sim.simulate_stream(banking, setup, learner, granularity, 0.2, 3, 2)


def test_simulator_invariants(events):
    passes = 2
    by_suite = {}
    for e in events:
        by_suite.setdefault(e.suite, []).append(e)
    for suite, rows in by_suite.items():
        blocks, attacks = sum(e.label == 'BLOCK' for e in rows), sum(e.attack for e in rows)
        unprotected, _ = sim.simulate_stream(rows, 'no_protection', 'none', 'none', 0.0, 0, passes)
        assert unprotected['executed_block'] == passes * blocks and unprotected['attacks_executed'] == passes * attacks
        fixed, _ = sim.simulate_stream(rows, 'fixed_rules', 'none', 'none', 0.4, 0, passes)
        assert fixed.get('auto_allowed', 0) == 0
    # Inside the Wall, memory only ever sees actions the Wall passed.
    assert all(e.wall_verdict == 'PASS' for e in events if sim.gate_path(e, 'learning_inside_wall')[0] == 'ASK')


def test_learner_receives_only_keys_and_answers(events, monkeypatch):
    seen = []

    class Spy(CountingMemory):
        def update(self, key, approved):
            seen.append((type(key), type(approved)))
            super().update(key, approved)

    monkeypatch.setattr(sim, 'build_memory', lambda config: Spy())
    sim.simulate_stream([e for e in events if e.suite == 'slack'], 'learning_inside_wall', 'counting', 'exact', 0.2, 0, 1)
    assert seen and set(seen) == {(str, bool)}
