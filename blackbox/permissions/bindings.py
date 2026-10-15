"""Controller-owned, single-use authorization ledger. Never accept model tokens."""
from dataclasses import dataclass
from uuid import uuid4

@dataclass(frozen=True)
class Binding:
    episode_id: str
    attempt_id: str
    action_id: str
    action_digest: str
    policy_version: str
    state_version: str
    schema_digest: str
    expires: float

    @classmethod
    def create(cls, episode, action, expires):
        return cls(episode.episode_id, episode.attempt_id, action.action_id, action.digest,
                   action.policy_version, action.state_version, action.schema_digest, expires)

    def matches(self, episode, action, now):
        return now < self.expires and self == Binding.create(episode, action, self.expires)

@dataclass
class Authorization:
    binding: Binding
    decision_id: str
    consumed: bool = False

class AuthorizationLedger:
    def __init__(self):
        self._entries = {}
        self.outcomes = {}
        self.attempts = {}

    def issue(self, binding, decision_id):
        if binding.action_id in self.attempts:
            raise ValueError('ATTEMPT_ALREADY_AUTHORIZED')
        token = uuid4().hex
        self._entries[token] = Authorization(binding, decision_id)
        self.attempts[binding.action_id] = binding
        return token

    def replay(self, episode, action):
        binding = self.attempts.get(action.action_id)
        if binding is None or binding != Binding.create(episode, action, binding.expires):
            raise ValueError('REDELIVERY_BINDING_MISMATCH')
        return self.outcomes[action.action_id]

    def consume(self, token, episode, action, now):
        entry = self._entries.get(token)
        if entry is None or entry.consumed or not entry.binding.matches(episode, action, now):
            raise ValueError('INVALID_OR_STALE_AUTHORIZATION')
        entry.consumed = True
        return entry
