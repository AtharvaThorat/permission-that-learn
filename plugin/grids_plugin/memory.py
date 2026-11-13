"""Permission memory: the repository's scoped grants and contextual learner (the team, 2026-11-11).

This wraps `grids.core.permissions.store.PermissionStore` and `provider.ScopedApprovalProvider` unchanged:

- A grant is issued only when the person chooses "Approve and remember". It covers exactly that request, tool,
  arguments, facts, policy version and schema; it expires (default 24 h) and can be revoked.
- A grant answers only laya-cybersec's own asks (NEEDS_CLARIFICATION, UNCERTAIN). Mandatory confirmations such as file
  shares, incomplete evidence and model failures always reach the person.
- A rejection revokes the matching grant. The executor rechecks the grant, the Wall and the exact action at dispatch.

Modes (the store's own): `grants` reuses matching grants; `shadow` asks every time while the learner records what it
would have done; `active` lets the learner choose between asking and reusing a valid grant.
"""
import json
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path

MODES = {'off': 'Off (always ask)', 'grants': 'Grants (reuse remembered permissions)',
         'shadow': 'Shadow (learner records, still asks)', 'active': 'Active (learner decides when to reuse)'}
USER = 'demo-user'   # the trusted local operator; the assistant's messages can never choose it
TARGETS = ('recipients', 'email', 'user', 'participants', 'recipient', 'url')


class Memory:
    """One permission store shared by every session, so permissions outlive a Workspace reset."""

    def __init__(self, path, user=USER):
        from grids.core.permissions.store import PermissionStore
        self.path = Path(path)
        self.store = PermissionStore(self.path)
        self.user = self.store.user(user)

    def provider(self, inner, mode, record=None):
        """The repository's ScopedApprovalProvider around the person's approval channel."""
        from grids.core.permissions.provider import ScopedApprovalProvider
        if mode not in MODES or mode == 'off':
            raise ValueError('memory mode must be grants, shadow or active')
        return ScopedApprovalProvider(inner, self.store, self.user, mode, False, record)

    @staticmethod
    def rememberable(pending):
        """Only the model's own asks with complete evidence can be answered by a grant later."""
        from grids.core.permissions.memory import ELIGIBLE_REASONS
        metadata = json.loads(pending.get('decision_metadata') or '{}')
        return (pending.get('reason') in ELIGIBLE_REASONS and not metadata.get('error_kind')
                and pending['action'].get('evidence_complete') and bool(pending.get('request')))

    def remember(self, pending_path, ttl_seconds=86400, max_uses=None):
        """Issue an exact grant from a waiting action's pending record (as `grids permissions grant` does)."""
        from grids.core.contracts import BoundAction
        from grids.core.permissions.store import scope_for
        pending = json.loads(Path(pending_path).read_text(encoding='utf-8'))
        if not self.rememberable(pending):
            raise ValueError('Only laya-cybersec asks with complete evidence can be remembered')
        action = BoundAction(**{f.name: pending['action'][f.name] for f in fields(BoundAction)})
        return self.store.issue(self.user, scope_for(pending['request'], action), ttl_seconds, max_uses)

    def grants(self):
        rows = []
        for grant in self.store.list(self.user):
            scope = json.loads(grant['scope'])
            arguments = scope['arguments']
            target = next((arguments[k] for k in TARGETS if arguments.get(k)), None)
            rows.append({'id': grant['id'], 'tool': scope['tool'], 'target': target, 'request': scope['request'],
                         'uses': grant['uses'], 'maximum': grant['maximum'],
                         'expires': datetime.fromtimestamp(grant['expires'], timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
                         'active': not grant['revoked'] and grant['expires'] > self.store.clock()})
        return rows

    def revoke(self, grant_id):
        return self.store.revoke(self.user, grant_id)
