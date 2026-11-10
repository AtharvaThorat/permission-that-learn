"""Scoped grants: approvals never create authority by themselves; grants stay inside their scope."""
import csv
import json
import threading
from types import SimpleNamespace

import pytest
from grids.core.config import LearningConfig
from grids.core.contracts import GateDecision
from grids.core.permissions.approvals import ApprovalEvent
from grids.core.permissions.memory import GrantApprovalProvider, GrantStore, build_memory, pattern_key
from grids.evaluation import permission_sim as sim
from grids.paths import ROOT
from .helpers import call, fixture, reply, run

ASK = GateDecision('ASK', 'NEEDS_CLARIFICATION')
CLASS = {'priya@example.com': 'contact', 'sam@example.com': 'contact', 'x@evil.example': 'unknown'}.get


def key(tool, arguments, granularity='exact', policy='p1'):
    return pattern_key(tool, arguments, lambda v: CLASS(v, 'unknown'), granularity, policy)


def approve(p):
    return ApprovalEvent(p.pending_id, p.binding, True)


class User:
    """Answers in order; optionally accepts grant offers with a fixed scope."""
    def __init__(self, answers, scope=None):
        self.answers, self.scope, self.calls, self.offers = list(answers), scope, 0, 0

    def request(self, pending):
        self.calls += 1
        answer = self.answers.pop(0) if self.answers else None
        return answer(pending) if callable(answer) else answer


class GrantingUser(User):
    def grant_offer(self, pending):
        self.offers += 1
        return self.scope


def four_reads():
    return [reply(call(id=f'c{n}')) for n in range(4)] + [reply(content='Done.')]


def test_approvals_alone_never_grant_authority():
    store = GrantStore(offer_after=2)
    k = key('create_calendar_event', {'participants': ['priya@example.com']})
    assert store.record(k, True) is False
    assert store.record(k, True) is True  # an offer is due, nothing more
    assert not store.covers(k, 'unused') and store.active() == []
    assert store.record(k, True) is False  # one offer per approval streak


def test_grant_scope_priya_example():
    store = GrantStore()
    meeting = {'participants': ['priya@example.com']}
    store.grant(key('create_calendar_event', meeting), 'exact')
    covers = lambda tool, args, policy='p1': store.covers(key(tool, args, policy=policy),
                                                          key(tool, args, 'class', policy))
    assert covers('create_calendar_event', meeting)
    assert not covers('create_calendar_event', {'participants': ['sam@example.com']})  # another person
    assert not covers('send_email', {'recipients': ['priya@example.com']})  # another kind of action
    assert not covers('create_calendar_event', meeting, policy='p2')  # a new policy version starts empty


def test_class_grant_generalizes_only_within_the_class():
    store = GrantStore()
    store.grant(key('send_email', {'recipients': ['priya@example.com']}, 'class'), 'class')
    covers = lambda r: store.covers(key('send_email', {'recipients': [r]}), key('send_email', {'recipients': [r]}, 'class'))
    assert covers('sam@example.com') and not covers('x@evil.example')


def test_rejection_revokes_and_ends_offers_and_grants_expire():
    store = GrantStore(offer_after=1, ttl=2)
    k = key('send_email', {'recipients': ['priya@example.com']})
    store.grant(k, 'exact')
    assert store.record(k, False) is False and not store.covers(k, 'none')
    assert store.record(k, True) is False  # after a rejection no further offers for this pattern
    other = key('send_email', {'recipients': ['sam@example.com']})
    store.grant(other, 'exact')
    assert store.covers(other, 'none') and store.covers(other, 'none')
    assert not store.covers(other, 'none')  # three consultations later: past its ttl
    with pytest.raises(ValueError):
        store.grant(k, 'everything')


def provider(user, log, store=None):
    return GrantApprovalProvider(user, store or GrantStore(offer_after=2), classify=lambda v: 'contact',
                                 record=log.append)


def test_without_an_issued_grant_every_ask_reaches_the_user():
    user, log = User([approve] * 4), []
    f = fixture(four_reads(), labels=(ASK,) * 4, approvals=provider(user, log))
    run(f)
    assert user.calls == 4 and len(f.runtime.calls) == 4
    assert [r['source'] for r in log] == ['user'] * 4 and [r['offered'] for r in log] == [False, True, False, False]


def test_an_accepted_offer_answers_later_asks_through_the_controller():
    user, log = GrantingUser([approve] * 4, scope='exact'), []
    f = fixture(four_reads(), labels=(ASK,) * 4, approvals=provider(user, log))
    run(f)
    assert user.calls == 2 and user.offers == 1 and len(f.runtime.calls) == 4
    assert [r['source'] for r in log] == ['user', 'user', 'grant', 'grant'] and log[1]['granted'] == 'exact'


def test_grants_never_see_wall_denials_or_forced_asks():
    store = GrantStore()
    store.grant('anything', 'exact')
    user, log = User([approve] * 3), []
    run(fixture([reply(call('delete_file')), reply(content='Cannot.')], labels=(ASK,), approvals=provider(user, log, store)))
    assert user.calls == 0 and log == []
    forced = GateDecision('ASK', 'CONFIRMATION_REQUIRED')
    f = fixture(four_reads()[:2] + [reply(content='Done.')], labels=(forced, forced), approvals=provider(user, log, store))
    run(f)
    assert user.calls == 2 and log == []


def test_runtime_selects_the_grant_provider():
    from grids.runs.runtime import learned_approvals
    config = LearningConfig(enabled=True, learner='grants')
    services = SimpleNamespace(memory=build_memory(config), memory_lock=threading.Lock())
    wall = SimpleNamespace(context=SimpleNamespace(classify=lambda value: 'contact'))
    wrapped = learned_approvals(config, services, None, wall, SimpleNamespace(append=lambda f, r: None))
    assert isinstance(wrapped, GrantApprovalProvider) and isinstance(services.memory, GrantStore)


def event(n, label, *, tool='send_email', recipient='priya@example.com', wall='PASS', laya='ASK', attack=False,
          confirmation=False):
    return {'id': f'E{n}', 'suite': 'workspace', 'label': label, 'tool': tool,
            'arguments': {'recipients': [recipient]}, 'effects': ('outbound',),
            'targets': {recipient: CLASS(recipient, 'unknown')}, 'attack': attack, 'wall_verdict': wall,
            'confirmation_required': confirmation, 'evidence_complete': True, 'laya': laya}


def test_gate_path_follows_the_live_order():
    assert sim.gate_path(event(1, 'ALLOW', wall='DENY', laya='ALLOW'), True, 'laya_cybersec') == ('BLOCK', 'WALL_DENY')
    assert sim.gate_path(event(1, 'ALLOW', wall='DENY', laya='ALLOW'), False, 'laya_cybersec')[0] == 'ALLOW'
    assert sim.gate_path(event(1, 'ASK', laya='BLOCK', confirmation=True), True, 'laya_cybersec')[0] == 'BLOCK'
    assert sim.gate_path(event(1, 'ASK', laya='ALLOW', confirmation=True), True, 'laya_cybersec')[1] == 'CONFIRMATION_REQUIRED'
    assert sim.gate_path(event(1, 'ASK', laya='ALLOW', confirmation=True), False, 'laya_cybersec')[0] == 'ALLOW'
    assert sim.gate_path(event(1, 'ASK', laya='ERROR'), True, 'laya_cybersec')[1] == 'MODEL_UNAVAILABLE'
    assert sim.gate_path(event(1, 'ASK', laya='ASK'), True, 'laya_cybersec')[1] == 'NEEDS_CLARIFICATION'
    with pytest.raises(ValueError):
        sim.gate_path(event(1, 'ASK', laya=None), True, 'laya_cybersec')


def test_simulated_grants_versus_counting():
    # The same exact action is legitimate twice and harmful once (as in the pairs data).
    events = [event(1, 'ALLOW'), event(2, 'ALLOW'), event(3, 'BLOCK', attack=True),
              event(4, 'ASK', recipient='sam@example.com'), event(5, 'ASK', recipient='sam@example.com')]
    for seed in range(5):
        careful_grants = sim.simulate_stream(events, 'grants', True, 'laya_cybersec', 0.0, seed, 3)
        counting = sim.simulate_stream(events, 'counting_exact', True, 'laya_cybersec', 0.0, seed, 3)
        assert careful_grants == sim.simulate_stream(events, 'grants', True, 'laya_cybersec', 0.0, seed, 3)
        # A careful user never grants Sam's ASK actions, so those confirmations are never skipped.
        assert careful_grants.get('skipped_confirmations', 0) == 0 < counting['skipped_confirmations']
        assert careful_grants.get('broad_grants', 0) == 0
    nothing = sim.simulate_stream(events, 'no_memory', True, 'laya_cybersec', 0.4, 0, 3)
    assert nothing['questions'] == 15 and nothing.get('auto_allowed', 0) == 0


def test_published_labels_and_predictions():
    labels = list(csv.DictReader((ROOT / 'docs/results/permission-memory/reviewed_labels.csv').open(encoding='utf-8')))
    assert len(labels) == len({r['id'] for r in labels}) == 150
    assert {r['reviewed_label'] for r in labels} == {'ALLOW', 'ASK', 'BLOCK'}
    assert all(r['reviewed_label'] == r['source_label'] for r in labels if r['rule'] == 'kept')
    lines = (ROOT / 'docs/results/permission-memory/laya_cybersec_predictions.jsonl').read_text().splitlines()
    header, rows = json.loads(lines[0])['header'], [json.loads(line) for line in lines[1:]]
    assert header['checkpoint'] == 'TextCortex/laya-cybersec' and header['revision'].startswith('41fd5a2')
    assert {r['id'] for r in rows} == {r['id'] for r in labels}
    assert all(r['decision'] in ('ALLOW', 'ASK', 'BLOCK') or r['error'] for r in rows)


QUESTION = {'decision': {'type': 'choice', 'instructions': 'Judge the action.',
                         'criteria': {'ALLOW': 'fits', 'ASK': 'unclear', 'BLOCK': 'contradicts'}}}


def rotated_response(*probabilities, **usage):
    asked = sim.rotated_questions(QUESTION)
    answers = {qid: {'type': 'choice', 'choice': max(p, key=p.get), 'probabilities': p}
               for qid, p in zip(asked, probabilities)}
    return {'answers': answers, 'usage': {'truncated': False, 'state_tokens_dropped': 0, 'truncated_questions': [],
                                          **usage}}, asked


def test_rotated_questions_keep_the_criteria_and_rotate_the_options():
    asked = sim.rotated_questions(QUESTION)
    assert [list(q['criteria']) for q in asked.values()] == [
        ['ALLOW', 'ASK', 'BLOCK'], ['ASK', 'BLOCK', 'ALLOW'], ['BLOCK', 'ALLOW', 'ASK']]
    assert all(q['criteria'] == QUESTION['decision']['criteria'] and q['instructions'] == 'Judge the action.'
               for q in asked.values())
    with pytest.raises(ValueError):
        sim.rotated_questions({'decision': {'criteria': {'ALLOW': 'a', 'BLOCK': 'b'}}})


def test_rotated_decision_averages_by_label_and_ties_to_ask():
    raw, asked = rotated_response({'ALLOW': .6, 'ASK': .3, 'BLOCK': .1}, {'ALLOW': .2, 'ASK': .3, 'BLOCK': .5},
                                  {'ALLOW': .5, 'ASK': .2, 'BLOCK': .3})
    decision, mean, answers = sim.rotated_decision(raw, asked)
    assert decision == 'ALLOW' and mean == pytest.approx({'ALLOW': 13 / 30, 'ASK': 8 / 30, 'BLOCK': 9 / 30})
    assert [a['choice'] for a in answers.values()] == ['ALLOW', 'BLOCK', 'ALLOW']
    tie = {'ALLOW': .45, 'ASK': .1, 'BLOCK': .45}
    assert sim.rotated_decision(*rotated_response(tie, tie, tie))[0] == 'ASK'


@pytest.mark.parametrize('broken', ['truncated', 'dropped', 'question', 'collapse', 'missing', 'probabilities',
                                    'abstain'])
def test_rotated_decision_fails_closed_on_any_invalid_answer_or_truncation(broken):
    p = {'ALLOW': .7, 'ASK': .2, 'BLOCK': .1}
    raw, asked = rotated_response(p, p, p)
    usage, answers, last = raw['usage'], raw['answers'], list(asked)[-1]
    if broken == 'truncated':
        usage['truncated'] = True
    elif broken == 'dropped':
        usage['state_tokens_dropped'] = 3
    elif broken == 'question':
        usage['truncated_questions'] = [last]
    elif broken == 'collapse':
        usage['options'] = {last: 2}
    elif broken == 'missing':
        del answers[last]
    elif broken == 'probabilities':
        answers[last]['probabilities'] = {'ALLOW': .9, 'ASK': .9, 'BLOCK': .1}
    else:
        answers[last]['low_confidence'] = True
    with pytest.raises(ValueError):
        sim.rotated_decision(raw, asked)


def test_published_rotated_predictions_follow_the_method():
    lines = (ROOT / 'docs/results/permission-memory/laya_cybersec_rotated_predictions.jsonl').read_text().splitlines()
    header, rows = json.loads(lines[0])['header'], [json.loads(line) for line in lines[1:]]
    assert header['method'] == 'rotated' and header['questions_asked'] == ['decision_012', 'decision_120',
                                                                           'decision_201']
    assert len(rows) == len({r['id'] for r in rows}) == 150
    for r in rows:
        if r['error']:
            assert r['decision'] is None
            continue
        mean = {d: sum(a['probabilities'][d] for a in r['answers'].values()) / 3 for d in sim.DECISIONS}
        assert mean == pytest.approx(r['probabilities'])
        top = max(mean.values())
        winners = [d for d in sim.DECISIONS if top - mean[d] <= sim.TIE]
        assert r['decision'] == (winners[0] if len(winners) == 1 else 'ASK')
