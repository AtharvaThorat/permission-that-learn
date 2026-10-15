from blackbox.contracts import GateDecision

class RulesGate:
    """Named comparator: read-only proposals auto-allow; all writes need approval.

    This is a declared coarse rule, not a claim of natural-language authorization.
    """
    def evaluate(self, episode, action, wall):
        if set(action.effects) <= {'read'}:
            return GateDecision('ALLOW', 'RULE_READ_ONLY', backend='rules_only')
        return GateDecision('ASK', 'RULE_WRITE_CONFIRMATION', backend='rules_only')

    def close(self):
        pass
