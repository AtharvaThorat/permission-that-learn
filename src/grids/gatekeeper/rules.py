"""Deterministic rules gatekeeper: a model-free stand-in behind the Wall.

Reads are allowed, destructive actions blocked, everything else (send, share, write,
pay) asked. Interruption and creep results then do not depend on a model's quality;
Laya can replace it through the same `evaluate` interface.
"""
from grids.core.contracts import GateDecision

READ_EFFECTS = frozenset({'read', 'mark_read'})


def rules_decision(effects):
    effects = set(effects)
    if effects and effects <= READ_EFFECTS:
        return 'ALLOW', 'TASK_AUTHORIZED'
    if 'destructive' in effects:
        return 'BLOCK', 'RULE_DESTRUCTIVE'
    return 'ASK', 'NEEDS_CLARIFICATION'


class RulesGate:
    def evaluate(self, episode, action, wall):
        decision, reason = rules_decision(action.effects)
        return GateDecision(decision, reason, backend='rules')

    def close(self):
        pass
