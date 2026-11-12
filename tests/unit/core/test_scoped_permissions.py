from dataclasses import replace
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from grids.core.actions import bind
from grids.core.contracts import GateDecision, Proposal, Outcome
from grids.core.permissions.approvals import ApprovalEvent, PendingApprovalProvider
from grids.core.permissions.bindings import Binding
from grids.core.permissions.provider import ScopedApprovalProvider
from grids.core.permissions.store import PermissionStore, scope_for
from grids.benchmarks.agentdojo.tools import NativeTools
from grids.evaluation.permission_checks import scenarios
from .helpers import fixture, run

P = {'ALLOW': .1, 'ASK': .8, 'BLOCK': .1}
ASK = GateDecision('ASK', 'NEEDS_CLARIFICATION', probabilities=P)
TASK = 'Read meeting notes and summarize.'


def prepared(tmp_path, mode='grants', inner=None):
    store = PermissionStore(tmp_path / 'permissions.sqlite')
    provider = ScopedApprovalProvider(inner or PendingApprovalProvider(), store, 'alice', mode)
    f = fixture(labels=(ASK,), approvals=provider)
    action = bind(Proposal('c', 'get_file_by_id', {'file_id': 'notes-7'}), 'a', NativeTools(f.runtime),
                  f.facts, f.wall, f.env, 10000)
    scope = scope_for(TASK, action)
    return store, provider, f, scope


def binding(n='a'):
    return Binding('ep', 'attempt', n, 'digest', 'policy', 'state', 'schema', 100000000000.)


def test_live_controller_uses_grant_and_records_outcome(tmp_path):
    store, provider, f, scope = prepared(tmp_path)
    store.issue('alice', scope)
    run(f)
    assert len(f.runtime.calls) == 1
    with store.transaction() as db:
        record = json.loads(db.execute('SELECT data FROM decisions').fetchone()['data'])
    assert record['action'] == 'USE_EXISTING_GRANT' and record['outcome']['executed']


def test_approvals_do_not_create_grants(tmp_path):
    class Approve:
        def request(self, p):
            return ApprovalEvent(p.pending_id, p.binding, True)
    store, provider, f, scope = prepared(tmp_path, inner=Approve())
    dispatches = 0
    for _ in range(3):
        f = fixture(labels=(ASK,), approvals=provider)
        run(f)
        dispatches += len(f.runtime.calls)
    assert dispatches == 3 and store.list('alice') == []


@pytest.mark.parametrize('field,value', [('request', 'Different authentic request'), ('tool', 'send_email'),
    ('arguments', {'file_id': 'other', 'recipient': 'stranger', 'amount': 1000}),
    ('facts', {'source': 'changed', 'recipients': ['stranger']}), ('policy_version', 'p2'), ('schema_digest', 's2')])
def test_exact_scope_binds_all_authorization_inputs(tmp_path, field, value):
    store, _, _, scope = prepared(tmp_path)
    store.issue('alice', scope)
    altered = {**scope, field: value}
    assert store.decide('alice', altered, binding(), P, ['read'], 'grants')[1] is None
    assert store.decide('bob', scope, binding(), P, ['read'], 'grants')[1] is None


@pytest.mark.parametrize('reason', ['CONFIRMATION_REQUIRED', 'INSUFFICIENT_EVIDENCE', 'MODEL_UNAVAILABLE',
                                   'APPLICATION_CHARACTER_BUDGET'])
def test_forced_asks_are_never_answered_by_grants(tmp_path, reason):
    store, _, f, scope = prepared(tmp_path)
    store.issue('alice', scope)
    f.gate.labels = iter([GateDecision('ASK', reason, probabilities=P)])
    run(f)
    assert not f.runtime.calls and f.pipeline.last_episode.terminal == 'pending_approval'


@pytest.mark.parametrize('change', ['wall', 'block', 'malformed', 'error', 'missing', 'confirmation', 'overflow'])
def test_security_checks_survive_matching_grant(tmp_path, change):
    store, _, f, scope = prepared(tmp_path)
    store.issue('alice', scope)
    if change == 'wall':
        f.wall.policy.allowed_effects = []
    elif change == 'block':
        f.gate.labels = iter([GateDecision('BLOCK', 'TASK_MISMATCH', probabilities=P)])
    elif change == 'malformed':
        f.gate.labels = iter([replace(ASK, probabilities={'ALLOW': float('nan')})])
    elif change == 'error':
        f.gate.labels = iter([replace(ASK, error_kind='truncation')])
    elif change == 'missing':
        f.facts.missing = True
    elif change == 'confirmation':
        f.wall.policy.confirmation_effects = ['read']
    else:
        f.pipeline.config.runtime.max_gate_chars = 1
    run(f)
    assert not f.runtime.calls


def test_revocation_expiry_and_restart_invalidate_reservations(tmp_path):
    store, _, _, scope = prepared(tmp_path)
    now = [100.]
    store.clock = lambda: now[0]
    grant = store.issue('alice', scope, ttl=10)
    _, permit, _ = store.decide('alice', scope, binding(), P, ['read'], 'grants')
    restarted = PermissionStore(store.path, clock=store.clock)
    assert restarted.list('alice')[0]['uses'] == 1
    with pytest.raises(ValueError):
        with restarted.dispatch_guard(permit, binding()):
            pytest.fail('restart replay')
    now[0] = 111
    with pytest.raises(ValueError):
        with store.dispatch_guard(permit, binding()):
            pytest.fail('expired dispatch')
    now[0] = 101
    store.revoke('alice', grant)
    with pytest.raises(ValueError):
        with store.dispatch_guard(permit, binding()):
            pytest.fail('revoked dispatch')


def test_atomic_use_limit_duplicate_binding_and_dispatch(tmp_path):
    store, _, _, scope = prepared(tmp_path)
    store.issue('alice', scope, maximum=1)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda n: store.decide('alice', scope, binding(str(n)), P, ['read'], 'grants'), range(2)))
    permits = [(n, r[1]) for n, r in enumerate(results) if r[1]]
    assert len(permits) == 1
    n, permit = permits[0]
    with store.dispatch_guard(permit, binding(str(n))):
        pass
    with pytest.raises(ValueError):
        with store.dispatch_guard(permit, binding(str(n))):
            pytest.fail('duplicate dispatch')
    store.issue('alice', scope)
    with pytest.raises(sqlite3.IntegrityError):
        store.decide('alice', scope, binding(str(n)), P, ['read'], 'grants')


def test_revocation_serializes_with_dispatch(tmp_path):
    store, _, _, scope = prepared(tmp_path)
    grant = store.issue('alice', scope)
    _, permit, _ = store.decide('alice', scope, binding(), P, ['read'], 'grants')
    attempted = threading.Event()
    def revoke():
        attempted.set()
        return store.revoke('alice', grant)
    with ThreadPoolExecutor(1) as pool:
        with store.dispatch_guard(permit, binding()):
            future = pool.submit(revoke)
            assert attempted.wait(2)
            assert not future.done()
        assert future.result(timeout=3)


def test_review_is_exactly_once_separate_from_approval_and_requires_consent(tmp_path):
    store, _, _, scope = prepared(tmp_path)
    store.issue('alice', scope)
    did, _, _ = store.decide('alice', scope, binding(), P, ['read'], 'grants')
    store.outcome('alice', did, Outcome(True, 'EXECUTED', 'ALLOW'))
    args = dict(user='alice', decision_id=did, feedback_id='f1', reviewer='operator', rationale='Verified context',
                preference='unwanted', authorization_label='ASK', consent=True, suitable=True,
                verified={'request': True, 'policy': True, 'outcome': True})
    assert store.review(**args)
    assert not store.review(**args)
    assert len(store.export('alice')) == 1 and store.export('bob') == []
    assert store.list('alice')[0]['revoked']
    with pytest.raises(ValueError):
        store.review(**{**args, 'user': 'bob'})


def test_learner_reproducible_isolated_frozen_and_no_shadow_rewards(tmp_path):
    store, _, _, scope = prepared(tmp_path)
    for user in ('alice', 'bob'):
        store.issue(user, scope)
    trajectories = []
    for user in ('alice', 'bob'):
        trajectories.append([store.decide(user, scope, binding(str(i)), P, ['read'], 'shadow')[2]['recommendation']
                             for i in range(20)])
    assert trajectories[0] == trajectories[1]
    with store.transaction() as db:
        before = store.state(db, 'alice')
        assert before['weights']['USE_EXISTING_GRANT'] == [0.] * 40
    store.decide('alice', scope, binding('holdout'), P, ['read'], 'shadow', frozen=True)
    with store.transaction() as db:
        assert before == store.state(db, 'alice')
    restarted = PermissionStore(store.path)
    with restarted.transaction() as db:
        assert before == restarted.state(db, 'alice')


def test_storage_failure_withholds_dispatch(tmp_path, monkeypatch):
    store, _, f, scope = prepared(tmp_path)
    store.issue('alice', scope)
    monkeypatch.setattr(store, 'decide', lambda *a, **k: (_ for _ in ()).throw(sqlite3.OperationalError('full')))
    run(f)
    assert not f.runtime.calls and f.pipeline.last_episode.terminal == 'infrastructure_error'


def test_constructed_set_balance():
    cases = scenarios()
    assert len(cases) == len({c['id'] for c in cases}) == 36
    for suite in ('workspace', 'slack', 'banking'):
        for label in ('ALLOW', 'ASK', 'BLOCK'):
            assert sum(c['suite'] == suite and c['expected_initial'] == label for c in cases) == 4


def test_feedback_requires_verified_outcome_and_does_not_invent_reward(tmp_path):
    store, _, _, scope = prepared(tmp_path)
    store.issue('alice', scope)
    chosen = None
    for n in range(20):
        did, permit, _ = store.decide('alice', scope, binding(str(n)), P, ['read'], 'active')
        if permit:
            chosen = did
            break
    assert chosen
    with store.transaction() as db:
        before = store.state(db, 'alice')
    with pytest.raises(ValueError):
        store.review('alice', chosen, 'missing-outcome', 'human', 'review', authorization_label='ALLOW',
                     consent=True, suitable=True, verified={'request': True, 'policy': True, 'outcome': True})
    store.review('alice', chosen, 'unknown-reward', 'human', 'No reliable outcome', preference=None)
    with store.transaction() as db:
        after = store.state(db, 'alice')
    assert after['weights'] == before['weights']


def test_reviewed_reuse_updates_only_observed_arm(tmp_path):
    store, _, _, scope = prepared(tmp_path)
    store.issue('alice', scope)
    for n in range(20):
        did, permit, _ = store.decide('alice', scope, binding(str(n)), P, ['read'], 'active')
        if permit:
            break
    assert permit
    store.outcome('alice', did, Outcome(True, 'EXECUTED', 'ALLOW'))
    with store.transaction() as db:
        before = store.state(db, 'alice')
    store.review('alice', did, 'unwanted', 'operator', 'User required an optional check', preference='unwanted')
    with store.transaction() as db:
        after = store.state(db, 'alice')
    assert before['weights']['ASK_USER'] == after['weights']['ASK_USER']
    assert before['weights']['USE_EXISTING_GRANT'] != after['weights']['USE_EXISTING_GRANT']
    assert store.list('alice')[0]['revoked']


def test_rejection_revokes_matching_grants_even_in_shadow(tmp_path):
    class Reject:
        def request(self, p):
            return ApprovalEvent(p.pending_id, p.binding, False)
    store, _, f, scope = prepared(tmp_path, mode='shadow', inner=Reject())
    store.issue('alice', scope)
    run(f)
    assert not f.runtime.calls and store.list('alice')[0]['revoked']


def test_audit_failure_before_dispatch_withholds_action(tmp_path, monkeypatch):
    store, _, f, scope = prepared(tmp_path)
    store.issue('alice', scope)
    original = store.audit
    def fail(db, event, data):
        if event == 'grant_dispatch_authorized':
            raise sqlite3.OperationalError('audit full')
        return original(db, event, data)
    monkeypatch.setattr(store, 'audit', fail)
    run(f)
    assert not f.runtime.calls
    assert store.list('alice')[0]['uses'] == 1  # uncertain/failed reservation is never recycled


def test_grant_expiration_during_final_audit_withholds_dispatch(tmp_path):
    store, _, f, scope = prepared(tmp_path)
    now = [100.]
    store.clock = lambda: now[0]
    store.issue('alice', scope, ttl=10)
    emit = f.audit.emit
    def slow_audit(event):
        if event['event'] == 'dispatch':
            now[0] = 111.
        emit(event)
    f.audit.emit = slow_audit
    run(f)
    assert not f.runtime.calls


def test_report_regeneration_preserves_traces_and_missing_values(tmp_path):
    from grids.evaluation.permission_checks import report
    rows = [{'id': mode, 'phase': 'holdout', 'mode': mode, 'expected': 'ASK', 'final': 'ASK',
             'executed': False, 'forbidden_dispatch': False, 'seconds': .01, 'cpu_seconds': .001,
             'reason': 'MODEL_UNAVAILABLE', 'grant_match': False, 'raw_laya': None, 'events': [], 'context': {}}
            for mode in ('off', 'grants', 'active')]
    path = tmp_path / 'actions.jsonl'
    path.write_text('\n'.join(json.dumps(r) for r in rows))
    original = path.read_bytes()
    report(tmp_path)
    assert path.read_bytes() == original
    assert 'MODEL_UNAVAILABLE' in (tmp_path / 'report.html').read_text()
    assert rows[0]['raw_laya'] is None


def test_native_result_objects_do_not_break_permission_outcomes(tmp_path):
    store, _, _, scope = prepared(tmp_path)
    did, _, _ = store.decide('alice', scope, binding(), P, ['read'])
    store.outcome('alice', did, Outcome(True, 'EXECUTED', 'ALLOW', result=object()))
    with store.transaction() as db:
        outcome = json.loads(db.execute('SELECT data FROM decisions').fetchone()['data'])['outcome']
    assert outcome['executed'] and 'result' not in outcome


def test_post_dispatch_storage_failure_preserves_execution_status(tmp_path, monkeypatch):
    store, _, f, scope = prepared(tmp_path)
    store.issue('alice', scope)
    monkeypatch.setattr(store, 'outcome', lambda *a: (_ for _ in ()).throw(sqlite3.OperationalError('full')))
    run(f)
    assert len(f.runtime.calls) == 1
    assert f.pipeline.last_episode.terminal == 'uncertain_execution'
