"""Per-user contextual policies, synthetic users and the learning simulation."""
import random
import json

import pytest
from grids.core.permissions.contextual import FEATURES, RULES, ContextualMemory, ContextualPolicy, Ridge, features
from grids.core.permissions.memory import GrantStore
from grids.evaluation import learning_sim as ls
from grids.evaluation import synthetic_users as su
from grids.evaluation import learning_data as ld


def solve(matrix, vector):
    """Gauss-Jordan solve for the test oracle."""
    n = len(vector)
    m = [row[:] + [vector[i]] for i, row in enumerate(matrix)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[p] = m[p], m[c]
        for r in range(n):
            if r != c:
                f = m[r][c] / m[c][c]
                m[r] = [a - f * b for a, b in zip(m[r], m[c])]
    return [m[i][n] / m[i][i] for i in range(n)]


def test_sherman_morrison_matches_a_direct_ridge_solve():
    rng, d = random.Random(3), 5
    model, xs, ys = Ridge(d, ridge=2.0), [], []
    for _ in range(40):
        x, y = [rng.uniform(-1, 1) for _ in range(d)], float(rng.random() < 0.5)
        model.update(x, y)
        xs.append(x)
        ys.append(y)
    a = [[2.0 * (i == j) + sum(x[i] * x[j] for x in xs) for j in range(d)] for i in range(d)]
    b = [sum(x[i] * y for x, y in zip(xs, ys)) for i in range(d)]
    assert model.theta == pytest.approx(solve(a, b), abs=1e-9)


def test_estimate_converges_to_the_true_weights():
    rng, truth, model = random.Random(5), [0.2, 0.5, -0.3], Ridge(3, ridge=0.1)
    for _ in range(3000):
        x = [1.0, rng.random(), rng.random()]
        model.update(x, sum(t * v for t, v in zip(truth, x)) + rng.gauss(0, 0.05))
    assert model.theta == pytest.approx(truth, abs=0.03)


def test_confident_rules_start_by_asking_and_learn_a_routine_pattern():
    x = features({'probabilities': {'ALLOW': .2, 'ASK': .5, 'BLOCK': .3}, 'effects': ['outbound'],
                  'reach': ['contact']}, (0, 0), (0, 0))
    assert len(x) == len(FEATURES)
    for rule in ('linucb', 'egreedy'):
        assert ContextualPolicy(rule, epsilon=0.0).decide(x) == 'ask'
    policy = ContextualPolicy('linucb', audit=0.0)
    for _ in range(200):
        policy.update(x, True)
    assert policy.decide(x) == 'allow'
    policy.update(x, False)
    for _ in range(20):
        policy.update(x, False)
    assert policy.decide(x) == 'ask'  # rejections pull it back below the threshold
    with pytest.raises(ValueError):
        ContextualPolicy('ucb')


def train(memory, user, version, n=200):
    for _ in range(n):
        memory.update(user, version, 'k', 'c', {'effects': ['outbound']}, True)


def test_users_and_policy_versions_are_isolated_unless_pooled():
    memory = ContextualMemory('linucb', audit=0.0)
    train(memory, 'a', 'v1')
    assert memory.decide('a', 'v1', 'k', 'c', {'effects': ['outbound']}) == 'allow'
    assert memory.decide('b', 'v1', 'k', 'c', {'effects': ['outbound']}) == 'ask'  # no cross-user effect
    assert memory.decide('a', 'v2', 'k', 'c', {'effects': ['outbound']}) == 'ask'  # new policy version: empty
    pooled = ContextualMemory('linucb', pooled=True, audit=0.0)
    train(pooled, 'a', 'v1')
    assert pooled.decide('b', 'v1', 'k', 'c', {'effects': ['outbound']}) == 'allow'


def test_remembered_rejections_only_tighten_and_a_grant_lifts_them():
    store = GrantStore(remember_rejections=True)
    store.grant('k', 'exact')
    store.grant('c', 'class')
    store.record('k', False, 'c')
    assert store.denies('k') and not store.covers('k', 'c')  # both grants revoked by the rejection
    store.grant('k', 'exact')
    assert not store.denies('k') and store.covers('k', 'c')


def test_prediction_cache_preserves_answers_and_rejects_changed_inputs(tmp_path, monkeypatch):
    inputs, metadata, out = (tmp_path / n for n in ('inputs.jsonl', 'meta.json', 'pred.jsonl'))
    inputs.write_text(json.dumps({'laya_input': 'authentic request and exact action'}) + '\n')
    metadata.write_text(json.dumps({'question_and_checkpoint_provenance':
        {'cybersec': {'checkpoint': 'fixture', 'revision': 'abc'}}, 'laya_question': {'q': {}}}))
    monkeypatch.setattr(ld, 'package_versions', lambda: {'fixture': '1'})
    monkeypatch.setattr(ld, 'laya_agent', lambda *args: object())
    monkeypatch.setattr(ld, 'predict_state', lambda *args: {
        'decision': 'ASK', 'error': None, 'probabilities': {'ALLOW': .1, 'ASK': .8, 'BLOCK': .1},
        'answers': {'q': {'choice': 'ASK', 'probabilities': [.1, .8, .1]}}})
    ld.predict_inputs([inputs], metadata, out, method='single')
    original = out.read_bytes()
    def forbidden(*args):
        raise AssertionError('Cache hit must not initialize a model')
    monkeypatch.setattr(ld, 'laya_agent', forbidden)
    ld.predict_inputs([inputs], metadata, out, method='single')
    assert out.read_bytes() == original
    assert next(iter(ld.load_input_predictions(out)[1].values()))['answers']['q']['choice'] == 'ASK'
    inputs.write_text(json.dumps({'laya_input': 'changed action'}) + '\n')
    with pytest.raises(ValueError, match='different provenance'):
        ld.predict_inputs([inputs], metadata, out, method='single')
    assert out.read_bytes() == original
    failed = tmp_path / 'failed.jsonl'
    ld.predict_inputs([inputs], metadata, failed, method='single')
    record = next(iter(ld.load_input_predictions(failed)[1].values()))
    assert record['decision'] is None and record['error_kind'] == 'initialization_error'
    with failed.open('a') as stream:
        stream.write(json.dumps(record) + '\n')
    with pytest.raises(ValueError, match='Duplicate'):
        ld.load_input_predictions(failed)


@pytest.fixture(scope='module')
def world(tmp_path_factory):
    out = tmp_path_factory.mktemp('world') / 'w'
    data = su.generate(seed=1, users=6, null_users=2, length=120, eval_size=120, canary_size=40)
    su.write(data, out)
    return out, data


def test_generator_is_deterministic_disjoint_and_judged_by_the_real_wall(world):
    path, data = world
    spec = json.loads((path / 'spec.json').read_text())
    assert all(ld.sha256(path / name) == digest for name, digest in spec['sha256'].items())
    again = su.generate(seed=1, users=6, null_users=2, length=120, eval_size=120, canary_size=40)
    assert all(data[s] == again[s] for s in su.SPLITS)
    su.check_disjoint(data['stream'], data['eval'], data['canary'])
    rows = data['stream'] + data['eval'] + data['canary']
    assert all(r['label'] == 'BLOCK' for r in rows if r['kind'] in ('unrequested', 'policy') or r['attack'])
    assert all(r['label'] == 'ALLOW' and r['user_answer'] for r in rows if r['kind'] in ('allow', 'read'))
    assert all(r['wall_verdict'] == 'PASS' for r in rows if r['kind'] in ('allow', 'read', 'ask'))
    assert all(r['wall_verdict'] == 'DENY' for r in rows if r['kind'] in ('policy', 'inject_external'))
    assert {r['label'] for r in data['canary']} == {'BLOCK'}
    assert not set(su.HIDDEN) & set(su.observe(rows[0]))


def summary(events, arm, gatekeeper='rules', p=0.0, seed=0, wall=True, settings=None):
    return {r['group']: r for r in ls.rows_of(ls.simulate(events, arm, wall, gatekeeper, p, seed, settings))}


def test_simulation_sanity_checks(world):
    path, _ = world
    events = ls.load_events(path, gatekeeper='oracle')
    for arm in ls.ARMS:  # an oracle gatekeeper decides every non-ASK row correctly
        assert summary(events, arm, 'oracle')['all']['unwanted_executed'] == summary(events, arm, 'oracle')['all'][
            'wrong_auto_allows']
    events = ls.load_events(path)
    nothing = summary(events, 'no_memory')
    never = summary(events, 'linucb_free', settings={'tau': 0.999999, 'audit': 0.0})
    assert never == nothing  # a policy that never allows reproduces no memory exactly
    for arm in ls.ARMS:
        log = []
        ls.simulate(events, arm, True, 'rules', 0.4, 0, log=log)
        denied = {e['id'] for e in events if e['wall_verdict'] != 'PASS'}
        assert not any(r['executed'] for r in log if r['id'] in denied)  # the Wall holds in every arm
        assert summary(events, arm, p=0.4) == summary(events, arm, p=0.4)  # same seed, same result


def test_guarded_policies_allow_only_inside_a_grant_and_never_on_null_users(world):
    path, _ = world
    events = ls.load_events(path)
    for rule in RULES:
        log = []
        ls.simulate(events, f'{rule}_guarded', True, 'rules', 0.0, 0, log=log)
        granted = {}
        for e, r in zip(events, log):
            if r['source'] == 'memory':
                assert granted.get((e['user'], e['exact'])) or granted.get((e['user'], e['broad']))
            if r.get('granted'):
                granted[(e['user'], e['exact'] if r['granted'] == 'exact' else e['broad'])] = True
            if r.get('approved') is False:
                granted.pop((e['user'], e['exact']), None)
                granted.pop((e['user'], e['broad']), None)
        # Null users have no stable preferences, so none of their ASK rows is ever answered for them. (A grant on
        # their routine explicit actions can still cover an identical agent error: the action-keyed limit.)
        assert not any(r['source'] == 'memory' and e['group'] == 'null' and e['kind'] == 'ask'
                       for e, r in zip(events, log))
