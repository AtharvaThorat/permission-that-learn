"""Teammate HarnessWall plus current bound resource labels; no fallback wall."""
from dataclasses import replace
import json
from blackbox.actions import digest
from blackbox.contracts import WallVerdict


class PtlWall:
    implementation = 'ptl'

    def __init__(self, config, context, suite='workspace'):
        from ptl.wall.harness import HarnessWall
        from ptl.wall import presets
        self.config = config
        self.context = context
        self.suite = suite
        from integrations.agentdojo.suites import inventory
        self.inventory = None if suite == 'workspace' else inventory(suite)
        self.confirm = sorted(set(config.confirm_capabilities) | ({'pay'} if suite == 'banking' else set()))
        self.policy = getattr(presets, config.ptl_preset)
        self.adapter = HarnessWall(self.policy, context, inventory=self.inventory, confirm_capabilities=self.confirm)

    @classmethod
    def from_clean_environment(cls, config, env, suite='workspace'):
        from ptl.wall.context import WallContext
        from integrations.agentdojo.suites import clean_context
        context = WallContext.from_agentdojo_env(env) if suite == 'workspace' else clean_context(suite, env)
        return cls(config, context, suite)

    @property
    def version(self):
        # Confirmation settings are behavior-relevant too.
        version = self.adapter.version + ':' + digest(self.config.confirm_capabilities)
        return version if self.inventory is None else version + ':' + digest(self.inventory.model_dump(mode='json')) + ':' + digest(self.confirm)

    def evaluate(self, action):
        from ptl.wall.harness import HarnessWall
        from ptl.wall.context import WallContext
        def stop(label, reason):
            return WallVerdict(label, reason, self.version, action.digest, action.state_version,
                               missing=(reason,) if label == 'UNRESOLVED' else ())
        if action.policy_version != self.version:
            return stop('DENY', 'WALL_VERSION_CHANGED')
        facts = json.loads(action.facts_json)
        if digest(facts) != action.state_version or facts.get('missing'):
            return stop('UNRESOLVED', 'MISSING_OR_CHANGED_FACTS')
        # Trust in identities stays frozen. Resource memberships are from the
        # current binding, also re-resolved by GuardedExecutor before dispatch.
        context = self.context.model_dump()
        context['event_participants'] = {}
        context['file_collaborators'] = {}
        if self.suite != 'workspace':
            context['native_resources'] = {}
        for resource in facts.get('resources', []):
            if resource['kind'] == 'event':
                context['event_participants'][resource['id']] = frozenset(resource['participants'])
            elif resource['kind'] == 'file':
                context['file_collaborators'][resource['id']] = frozenset(
                    [resource['owner'], *resource['shared_with']])
            elif resource['kind'] in ('channel', 'transaction'):
                context['native_resources'].setdefault(resource['kind'], {})[resource['id']] = frozenset(resource['recipients'])
        current = HarnessWall(self.policy, type(self.context).model_validate(context), inventory=self.inventory,
                              confirm_capabilities=self.confirm)
        result = current.evaluate(replace(action, policy_version=current.version))
        return replace(result, policy_version=self.version)


def build_wall(config, suite='workspace'):
    if config.implementation == 'reference':
        from .wall import ReferenceWall
        return ReferenceWall.from_file(config.policy_path)
    # Legacy factory callers get an explicitly clean snapshot. The experiment
    # runner supplies a task-initialized clean snapshot through Dependencies.
    from agentdojo.task_suite.load_suites import get_suite
    env = get_suite('v1.2.2', suite).load_and_inject_default_environment({})
    return PtlWall.from_clean_environment(config, env, suite)
