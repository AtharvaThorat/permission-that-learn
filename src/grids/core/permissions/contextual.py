"""Per-user contextual policies for judgment asks: LinUCB, linear Thompson sampling, epsilon-greedy.

Feedback here is one-sided: the user answers only when asked, and an automatic allow returns no label.
Asking is therefore both the safe arm and the informative one. Textbook optimism would try the risky arm
(allow) under uncertainty and then learn nothing from it, so every rule below allows only when a
pessimistic or sampled estimate of "this user would approve" clears the break-even threshold
`tau = 1 - ask_cost / wrong_allow_cost`; otherwise it asks. Exploration means asking.

All rules share one ridge regression per user of the answer (1 approved, 0 rejected) on the context, and
differ only in how they use its uncertainty:

  linucb    allow iff  mean - alpha * sd >= tau          (lower confidence bound)
  lints     allow iff  mean + alpha * sd * N(0,1) >= tau (one posterior sample of the score)
  egreedy   allow iff  mean >= tau, except ask anyway with probability epsilon

With no answers yet, `linucb` and `egreedy` always ask. `lints` is the textbook rule and can allow from its
prior alone, which is the cost of posterior sampling when the uncertain arm is the unsafe one.
`audit` keeps a small share of would-be allows as questions, so a changed preference is noticed.
State is strictly per user and policy version; `pooled=True` exists only to measure what sharing costs.
These policies never see a Wall denial, a gatekeeper BLOCK or a forced ask: the caller consults them only
for judgment asks, and in the guarded design an allow additionally needs a live user grant.
Pure Python on purpose: the core package has no numerical dependency, and the dimension is small.
"""
import math
import random

RULES = ('linucb', 'lints', 'egreedy')
EFFECT_FLAGS = ('outbound', 'calendar_write', 'file_write', 'authority_write')
FEATURES = ('bias', 'p_allow', 'p_ask', 'p_block', 'unanimous', *EFFECT_FLAGS, 'reach_internal', 'reach_contact',
            'reach_outside', 'exact_approvals', 'exact_rejections', 'exact_seen', 'class_approvals',
            'class_rejections')


def features(context, exact, broad):
    """Context vector from what is verified at decision time and the user's own answer counts.

    `context`: `probabilities` (gatekeeper ALLOW/ASK/BLOCK, or None), `unanimous`, `effects`, `reach`
    (trust classes the action reaches). `exact` and `broad` are (approvals, rejections) of this user for the
    exact pattern and for its trust-class pattern. Labels and hidden preferences are never inputs.
    """
    probs = context.get('probabilities') or {}
    effects, reach = set(context.get('effects') or ()), set(context.get('reach') or ())
    return [1.0, float(probs.get('ALLOW', 0.0)), float(probs.get('ASK', 0.0)), float(probs.get('BLOCK', 0.0)),
            1.0 if context.get('unanimous') else 0.0,
            *(1.0 if flag in effects else 0.0 for flag in EFFECT_FLAGS),
            1.0 if 'internal' in reach else 0.0, 1.0 if 'contact' in reach else 0.0,
            1.0 if reach & {'external', 'unknown'} else 0.0,
            min(exact[0], 5) / 5, min(exact[1], 2) / 2, 1.0 if exact[0] + exact[1] else 0.0,
            min(broad[0], 10) / 10, min(broad[1], 3) / 3]


class Ridge:
    """Ridge regression kept as A^-1 and b; one observation costs O(d^2) (Sherman-Morrison)."""

    def __init__(self, dimension, ridge=1.0):
        self.d, self.n = dimension, 0
        self.inverse = [[(1.0 / ridge if i == j else 0.0) for j in range(dimension)] for i in range(dimension)]
        self.b, self.theta = [0.0] * dimension, [0.0] * dimension

    def _times(self, x):
        return [sum(row[j] * x[j] for j in range(self.d)) for row in self.inverse]

    def mean(self, x):
        return sum(t * v for t, v in zip(self.theta, x))

    def variance(self, x):
        return max(0.0, sum(a * v for a, v in zip(self._times(x), x)))

    def update(self, x, y):
        ax = self._times(x)
        scale = 1.0 + sum(a * v for a, v in zip(ax, x))
        for i in range(self.d):
            row, factor = self.inverse[i], ax[i] / scale
            for j in range(self.d):
                row[j] -= factor * ax[j]
        for i in range(self.d):
            self.b[i] += y * x[i]
        self.theta = self._times(self.b)
        self.n += 1


class ContextualPolicy:
    """One user's policy: asks until the chosen rule is confident the user would approve."""

    def __init__(self, rule='linucb', *, tau=0.9, alpha=0.3, epsilon=0.1, audit=0.02, ridge=1.0, seed=0,
                 dimension=len(FEATURES)):
        if rule not in RULES:
            raise ValueError(f'Unknown rule: {rule}')
        if not 0 < tau < 1 or alpha < 0 or not 0 <= epsilon < 1 or not 0 <= audit < 1:
            raise ValueError('tau in (0,1), alpha >= 0, epsilon and audit in [0,1) are required')
        self.rule, self.tau, self.alpha, self.epsilon, self.audit = rule, tau, alpha, epsilon, audit
        self.model, self.rng = Ridge(dimension, ridge), random.Random(seed)

    def score(self, x):
        """The quantity compared with tau. Deterministic for linucb and egreedy; one draw for lints."""
        mean = self.model.mean(x)
        if self.rule == 'egreedy':
            return mean
        spread = self.alpha * math.sqrt(self.model.variance(x))
        return mean - spread if self.rule == 'linucb' else mean + spread * self.rng.gauss(0.0, 1.0)

    def decide(self, x):
        if self.score(x) < self.tau:
            return 'ask'
        keep_asking = self.epsilon if self.rule == 'egreedy' else self.audit
        return 'ask' if keep_asking and self.rng.random() < keep_asking else 'allow'

    def update(self, x, approved):
        self.model.update(x, 1.0 if approved else 0.0)


class ContextualMemory:
    """Per-user policies and answer counts. A new policy version starts empty, as grants do."""

    def __init__(self, rule='linucb', *, pooled=False, seed=0, **settings):
        ContextualPolicy(rule, **settings)  # validate once
        self.rule, self.pooled, self.seed, self.settings = rule, pooled, seed, settings
        self.policies, self.counts = {}, {}

    def _owner(self, user, version):
        return ('*' if self.pooled else str(user), str(version))

    def policy(self, user, version):
        owner = self._owner(user, version)
        if owner not in self.policies:
            self.policies[owner] = ContextualPolicy(
                self.rule, seed=random.Random(f'{self.seed}|{owner[0]}|{owner[1]}').random(), **self.settings)
        return self.policies[owner]

    def vector(self, user, version, exact, broad, context):
        counts = self.counts.get(self._owner(user, version), {})
        return features(context, counts.get(exact, (0, 0)), counts.get(broad, (0, 0)))

    def decide(self, user, version, exact, broad, context):
        """'allow' or 'ask' for a judgment ask of this user; never called for anything else."""
        return self.policy(user, version).decide(self.vector(user, version, exact, broad, context))

    def confident(self, user, version, exact, broad, context):
        """True when the policy would allow, ignoring audit draws: the moment to offer a grant."""
        policy = self.policy(user, version)
        x = self.vector(user, version, exact, broad, context)
        if policy.rule == 'linucb':
            return policy.score(x) >= policy.tau
        return policy.model.mean(x) >= policy.tau

    def update(self, user, version, exact, broad, context, approved):
        """Learn one real user answer. The context is taken before the counts change."""
        x = self.vector(user, version, exact, broad, context)
        self.policy(user, version).update(x, approved)
        counts = self.counts.setdefault(self._owner(user, version), {})
        for key in {exact, broad}:
            a, r = counts.get(key, (0, 0))
            counts[key] = (a + 1, r) if approved else (a, r + 1)
