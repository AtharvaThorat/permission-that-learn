"""Approval memory: answers repeated judgment asks from the user's earlier answers.

It wraps an ApprovalProvider, which the controller calls only after a Wall PASS and a
gatekeeper decision that is not BLOCK, so memory can never move the Wall or overrule a
BLOCK. It answers only judgment asks (`ELIGIBLE_REASONS`); mandatory confirmations,
incomplete evidence and model failures always reach the user. A remembered answer is an
ordinary ApprovalEvent bound to the exact pending action, so execution keeps the
single-use ledger and the executor's Wall recheck. Learners see only the user's answers.

Two kinds of memory: counting/bandit learners turn repeated approvals into automatic
allows; `GrantStore` never does. With grants, approvals are preference statistics that can
only prompt an offer, and an action is allowed without asking only under a scoped grant
the user explicitly issued (bound to tool, people and resources or their trust classes,
policy version, and an optional expiry; revoked when the user rejects a covered action).
"""
import json
import random
import threading
from dataclasses import dataclass
from grids.core.actions import canonical
from .approvals import ApprovalEvent

ELIGIBLE_REASONS = frozenset({'NEEDS_CLARIFICATION', 'UNCERTAIN'})
TARGET_ARGS = ('recipient', 'recipients', 'cc', 'bcc', 'user', 'user_email', 'email', 'participants', 'url')
RESOURCE_ARGS = ('file_id', 'event_id', 'email_id', 'channel', 'id')


def _scalars(value):
    if isinstance(value, dict):
        return [v for item in value.values() for v in _scalars(item)]
    if isinstance(value, list):
        return [v for item in value for v in _scalars(item)]
    return [] if value is None or isinstance(value, bool) else [str(value)]


def pattern_key(tool, arguments, classify, granularity, policy_version):
    """`exact`: the same tool on the same people and resources. `class`: the same tool on
    the same kinds of people (trust classes), which generalizes and is where creep shows."""
    targets = sorted({v for name in TARGET_ARGS for v in _scalars(arguments.get(name))})
    if granularity == 'exact':
        resources = sorted(f'{name}={arguments[name]}' for name in RESOURCE_ARGS if arguments.get(name) is not None)
        return canonical([policy_version, tool, targets, resources])
    if granularity == 'class':
        classes = {str(getattr(c, 'value', c)) for c in map(classify, targets)}
        return canonical([policy_version, tool, sorted(classes) or ['none']])
    raise ValueError('Unknown memory granularity')


@dataclass
class Record:
    approvals: int = 0
    rejections: int = 0
    last: int = 0


class CountingMemory:
    """Allow after `approvals_to_allow` approvals with no rejection; block after
    `rejections_to_block` rejections (memory may only tighten on rejection). A rejection
    clears earlier approvals; a record unused for `ttl` consultations is forgotten."""

    def __init__(self, approvals_to_allow=2, rejections_to_block=1, ttl=None):
        self.k, self.r, self.ttl = approvals_to_allow, rejections_to_block, ttl
        self.records, self.tick = {}, 0

    def decide(self, key):
        self.tick += 1
        record = self.records.get(key)
        if record and self.ttl and self.tick - record.last > self.ttl:
            del self.records[key]
            record = None
        if record is None:
            return 'ask'
        if record.rejections >= self.r:
            return 'block'
        return 'allow' if record.approvals >= self.k and record.rejections == 0 else 'ask'

    def update(self, key, approved):
        record = self.records.setdefault(key, Record())
        record.last = self.tick
        if approved:
            record.approvals += 1
        else:
            record.rejections += 1
            record.approvals = 0

    def allowed(self):
        return sorted(k for k, r in self.records.items() if r.rejections == 0 and r.approvals >= self.k)


class BanditMemory:
    """Contextual Thompson sampling over {allow, ask} per key: Beta(approvals, rejections).
    Allow when a sampled approval rate beats 1 - ask_cost / wrong_allow_cost, the break-even
    for asking; `explore` keeps asking now and then so it keeps receiving answers."""

    def __init__(self, ask_cost=1.0, wrong_allow_cost=10.0, explore=0.1, seed=0, ttl=None):
        self.threshold = 1 - ask_cost / wrong_allow_cost
        self.explore, self.ttl, self.rng = explore, ttl, random.Random(seed)
        self.records, self.tick = {}, 0

    def decide(self, key):
        self.tick += 1
        record = self.records.get(key)
        if record and self.ttl and self.tick - record.last > self.ttl:
            del self.records[key]
            record = None
        if record is None:
            return 'ask'
        sample = self.rng.betavariate(1 + record.approvals, 1 + record.rejections)
        return 'allow' if sample > self.threshold and self.rng.random() >= self.explore else 'ask'

    def update(self, key, approved):
        record = self.records.setdefault(key, Record())
        record.last = self.tick
        if approved:
            record.approvals += 1
        else:
            record.rejections += 1

    def allowed(self):
        """Keys whose expected approval rate is past the threshold (deterministic, for reporting)."""
        return sorted(k for k, r in self.records.items()
                      if (1 + r.approvals) / (2 + r.approvals + r.rejections) > self.threshold)


@dataclass
class Grant:
    key: str
    scope: str  # 'exact' or 'class'
    issued: int
    expires: int | None = None
    uses: int = 0
    revoked: bool = False


class GrantStore:
    """Explicit, scoped, expiring grants plus approval statistics that only suggest them.

    `record` returns True when an offer is due: the `offer_after`-th approval of one exact
    pattern with no rejection and no live grant (once per streak; any rejection ends offers for
    that pattern). Only `grant`, the user's own act, creates authority.

    With `remember_rejections`, a rejected exact pattern is refused without asking from then on
    (`denies`). That only tightens: it never allows anything, and a later explicit grant of the
    same pattern lifts it.
    """

    def __init__(self, offer_after=2, ttl=None, remember_rejections=False):
        self.offer_after, self.ttl, self.remember_rejections = offer_after, ttl, remember_rejections
        self.stats, self.grants, self.denied, self.tick = {}, {}, set(), 0

    def _live(self, grant):
        return not grant.revoked and (grant.expires is None or self.tick <= grant.expires)

    def covers(self, exact, broad):
        self.tick += 1
        for key in (exact, broad):
            grant = self.grants.get(key)
            if grant and self._live(grant) and (grant.scope == 'exact') == (key == exact):
                grant.uses += 1
                return True
        return False

    def denies(self, exact):
        return exact in self.denied

    def record(self, exact, approved, broad=None):
        """Count one user answer. A rejection revokes the exact grant and, if given, the class grant."""
        record = self.stats.setdefault(exact, Record())
        record.last = self.tick
        if approved:
            record.approvals += 1
        else:
            record.rejections += 1
            record.approvals = 0
            for key in (exact, broad):
                if key in self.grants:
                    self.grants[key].revoked = True
            if self.remember_rejections:
                self.denied.add(exact)
        live = exact in self.grants and self._live(self.grants[exact])
        return approved and not live and record.rejections == 0 and record.approvals == self.offer_after

    def grant(self, key, scope):
        if scope not in ('exact', 'class'):
            raise ValueError('Unknown grant scope')
        self.denied.discard(key)
        self.grants[key] = Grant(key, scope, self.tick, None if self.ttl is None else self.tick + self.ttl)

    def revoke(self, key):
        if key in self.grants:
            self.grants[key].revoked = True

    def active(self):
        return sorted((g.key, g.scope) for g in self.grants.values() if self._live(g))


def build_memory(config):
    if config.learner == 'grants':
        return GrantStore(config.approvals_to_allow, config.ttl)
    if config.learner == 'counting':
        return CountingMemory(config.approvals_to_allow, config.rejections_to_block, config.ttl)
    return BanditMemory(config.ask_cost, config.wrong_allow_cost, config.explore, config.seed, config.ttl)


class MemoryApprovalProvider:
    """Answers an eligible ask from memory, else asks `inner` (the user) and learns the answer."""

    def __init__(self, inner, memory, *, classify, granularity='exact', record=None, lock=None,
                 eligible_reasons=ELIGIBLE_REASONS):
        self.inner, self.memory, self.classify, self.granularity = inner, memory, classify, granularity
        self.record, self.lock = record, lock or threading.Lock()
        self.eligible = frozenset(eligible_reasons)

    def _log(self, pending, key, source, approved):
        if self.record:
            self.record({'pending_id': pending.pending_id, 'action_id': pending.binding.action_id,
                         'tool': pending.action.tool, 'reason': pending.reason, 'key': key,
                         'source': source, 'approved': approved})

    def request(self, pending):
        if pending.reason not in self.eligible:
            return self.inner.request(pending)
        key = pattern_key(pending.action.tool, json.loads(pending.action.arguments_json), self.classify,
                          self.granularity, pending.binding.policy_version)
        with self.lock:
            choice = self.memory.decide(key)
        if choice in ('allow', 'block'):
            self._log(pending, key, 'memory', choice == 'allow')
            return ApprovalEvent(pending.pending_id, pending.binding, choice == 'allow')
        event = self.inner.request(pending)
        # Learn only from an answer bound to this exact pending action.
        if (isinstance(event, ApprovalEvent) and type(event.approved) is bool
                and event.pending_id == pending.pending_id and event.binding == pending.binding):
            with self.lock:
                self.memory.update(key, event.approved)
            self._log(pending, key, 'user', event.approved)
        return event


class GrantApprovalProvider:
    """Answers an eligible ask only under a live user grant; otherwise asks `inner`.

    When an approval makes an offer due, `inner.grant_offer(pending)` (if the channel has
    one) returns the scope the user chooses, 'exact' or 'class', or None to decline. The
    file operator channel has no such method, so live grants are then offered and logged,
    never issued.
    """

    def __init__(self, inner, store, *, classify, record=None, lock=None, eligible_reasons=ELIGIBLE_REASONS):
        self.inner, self.store, self.classify = inner, store, classify
        self.record, self.lock = record, lock or threading.Lock()
        self.eligible = frozenset(eligible_reasons)

    def _log(self, pending, keys, source, approved, **extra):
        if self.record:
            self.record({'pending_id': pending.pending_id, 'action_id': pending.binding.action_id,
                         'tool': pending.action.tool, 'reason': pending.reason, 'key': keys[0], 'class_key': keys[1],
                         'source': source, 'approved': approved, **extra})

    def request(self, pending):
        if pending.reason not in self.eligible:
            return self.inner.request(pending)
        arguments = json.loads(pending.action.arguments_json)
        keys = tuple(pattern_key(pending.action.tool, arguments, self.classify, g, pending.binding.policy_version)
                     for g in ('exact', 'class'))
        with self.lock:
            covered = self.store.covers(*keys)
        if covered:
            self._log(pending, keys, 'grant', True)
            return ApprovalEvent(pending.pending_id, pending.binding, True)
        event = self.inner.request(pending)
        if not (isinstance(event, ApprovalEvent) and type(event.approved) is bool
                and event.pending_id == pending.pending_id and event.binding == pending.binding):
            return event
        with self.lock:
            offer = self.store.record(keys[0], event.approved)
        scope = None
        if offer and callable(getattr(self.inner, 'grant_offer', None)):
            scope = self.inner.grant_offer(pending)
            if scope is not None:
                with self.lock:
                    self.store.grant(keys[0] if scope == 'exact' else keys[1], scope)
        self._log(pending, keys, 'user', event.approved, offered=offer, granted=scope)
        return event
