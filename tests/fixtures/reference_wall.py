"""Reference deterministic engine, NOT the wall teammate's authoritative policy."""
import json
import re
from pathlib import Path
from typing import Protocol
from pydantic import Field
from grids.core.actions import digest
from grids.core.config import Strict
from grids.core.contracts import WallVerdict

class Policy(Strict):
    policy_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    allowed_effects: list[str]
    denied_effects: list[str] = Field(default_factory=lambda: ['destructive', 'authority_write'])
    confirmation_effects: list[str] = Field(default_factory=list)
    approved_addresses: list[str] = Field(default_factory=list)
    approved_domains: list[str] = Field(default_factory=list)
    resource_scopes: dict[str, list[str]] = Field(default_factory=dict)
    require_labels: bool = False
    allowed_labels: list[str] = Field(default_factory=lambda: ['public', 'internal'])

def address(value):
    # Exact mailbox policy: display names, comments, wildcards and subdomain suffix
    # matching are unsupported. Preserve local-part case and original execution args.
    if not isinstance(value, str) or not re.fullmatch(r'[^\s@<>(),;]+@[^\s@<>(),;]+\.[^\s@<>(),;]+', value):
        raise ValueError('UNRESOLVED_RECIPIENT')
    local, domain = value.rsplit('@', 1)
    return local + '@' + domain.lower()

class Wall(Protocol):
    @property
    def version(self) -> str: ...
    def evaluate(self, action) -> WallVerdict: ...

class ReferenceWall:
    implementation = 'reference'

    def __init__(self, policy):
        self.policy = policy

    @classmethod
    def from_file(cls, path):
        return cls(Policy.model_validate(json.loads(Path(path).read_text(encoding='utf-8'))))

    @property
    def version(self):
        return self.policy.policy_id + ':' + self.policy.version + ':' + digest(self.policy.model_dump())

    def evaluate(self, action):
        policy = self.policy
        facts = json.loads(action.facts_json)
        def verdict(label, reason, missing=()):
            return WallVerdict(label, reason, self.version, action.digest, action.state_version,
                               bool(set(action.effects) & set(policy.confirmation_effects)), tuple(missing))
        if action.policy_version != self.version:
            return verdict('DENY', 'STALE_POLICY')
        if set(action.effects) & set(policy.denied_effects) or not set(action.effects) <= set(policy.allowed_effects):
            return verdict('DENY', 'FORBIDDEN_EFFECT')
        if facts.get('missing'):
            return verdict('UNRESOLVED', 'MISSING_FACTS', facts['missing'])
        try:
            approved = {address(a) for a in policy.approved_addresses}
            domains = {d.lower() for d in policy.approved_domains}
            for recipient in facts.get('recipients', []):
                mailbox = address(recipient)
                if mailbox not in approved and mailbox.rsplit('@', 1)[1] not in domains:
                    return verdict('DENY', 'RECIPIENT_OUTSIDE_POLICY')
        except ValueError:
            return verdict('UNRESOLVED', 'UNRESOLVED_RECIPIENT', ('recipient_identity',))
        for resource in facts.get('resources', []):
            scope = policy.resource_scopes.get(resource['kind'])
            if scope is not None and resource['id'] not in scope:
                return verdict('DENY', 'RESOURCE_OUTSIDE_SCOPE')
            label = resource.get('label')
            if policy.require_labels and label is None:
                return verdict('UNRESOLVED', 'MISSING_LABEL', (resource['kind'] + ':' + resource['id'],))
            if label is not None and label not in policy.allowed_labels:
                return verdict('DENY', 'RESOURCE_SENSITIVITY')
        return verdict('PASS', 'REFERENCE_POLICY_PASS')
