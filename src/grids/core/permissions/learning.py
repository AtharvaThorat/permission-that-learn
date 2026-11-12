"""Small per-user contextual cost learner; it never creates authority."""
import hashlib
import math
import random
import json

ARMS = ('ASK_USER', 'USE_EXISTING_GRANT')
DIM = 40


def features(probabilities, tool, effects, facts, age, reviewed):
    if (not isinstance(probabilities, dict) or set(probabilities) != {'ALLOW', 'ASK', 'BLOCK'}
            or any(type(p) not in (float, int) or not math.isfinite(p) or not 0 <= p <= 1
                   for p in probabilities.values()) or abs(sum(probabilities.values()) - 1) > .002):
        raise ValueError('INVALID_PROBABILITIES')
    x = [0.] * DIM
    x[:6] = [1., *[probabilities[k] for k in ('ALLOW', 'ASK', 'BLOCK')],
             min(1., max(0., age) / 86400), min(1., reviewed / 100)]
    # Only trusted categorical metadata. Raw prompt/tool-result text is not a feature.
    categories = [tool, *effects, str(facts.get('source', 'unknown'))]
    for category in categories:
        slot = 6 + int(hashlib.sha256(category.encode()).hexdigest()[:8], 16) % (DIM - 6)
        x[slot] = 1.
    return x


def initial():
    return {'version': 0, 'feature_version': 1, 'observations': 0, 'reviewed': 0,
            'weights': {a: [0.] * DIM for a in ARMS}, 'rng': json.loads(json.dumps(random.Random(42).getstate()))}


def tuples(value):
    return tuple(tuples(v) for v in value) if isinstance(value, (list, tuple)) else value


def choose(state, x, available, frozen=False):
    rng = random.Random()
    rng.setstate(tuples(state['rng']))
    if not available or state['observations'] < 10:
        action, propensity = ARMS[0], 1.
    else:
        costs = {a: max(0., min(10., sum(w * v for w, v in zip(state['weights'][a], x)))) for a in ARMS}
        best = min(ARMS, key=lambda a: costs[a])  # ties ask
        action = rng.choice(ARMS) if rng.random() < .1 else best
        propensity = .95 if action == best else .05
    if not frozen:
        state['rng'] = json.loads(json.dumps(rng.getstate()))
        state['observations'] += int(available)
    return action, propensity


def update(state, action, x, cost):
    weights = state['weights'][action]
    prediction = sum(w * v for w, v in zip(weights, x))
    scale = .05 * (cost - prediction) / max(1., sum(v * v for v in x))
    state['weights'][action] = [max(-10., min(10., w + scale * v)) for w, v in zip(weights, x)]
    state['version'] += 1
