"""Teammate HarnessWall plus current bound resource labels; no fallback wall."""
from dataclasses import replace
import json
from blackbox.actions import digest
from blackbox.contracts import WallVerdict


class PtlWall:
    implementation = 'ptl'

    def __init__(self, config, context):
        from ptl.wall.harness import HarnessWall
        from ptl.wall import presets
        self.config = config
        self.context = context
        self.policy = getattr(presets, config.ptl_preset)
        self.adapter = HarnessWall(self.policy, context, confirm_capabilities=config.confirm_capabilities)

    @classmethod
    def from_clean_environment(cls, config, env):
        from ptl.wall.context import WallContext
        return cls(config, WallContext.from_agentdojo_env(env))

    @property
    def version(self):
        # Confirmation settings are behavior-relevant too.
        return self.adapter.version + ':' + digest(self.config.confirm_capabilities)

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
        for resource in facts.get('resources', []):
            if resource['kind'] == 'event':
                context['event_participants'][resource['id']] = frozenset(resource['participants'])
            elif resource['kind'] == 'file':
                context['file_collaborators'][resource['id']] = frozenset(
                    [resource['owner'], *resource['shared_with']])
        current = HarnessWall(self.policy, WallContext.model_validate(context),
                              confirm_capabilities=self.config.confirm_capabilities)
        result = current.evaluate(replace(action, policy_version=current.version))
        return replace(result, policy_version=self.version)


def build_wall(config):
    if config.implementation == 'reference':
        from .wall import ReferenceWall
        return ReferenceWall.from_file(config.policy_path)
    # Legacy factory callers get an explicitly clean snapshot. The experiment
    # runner supplies a task-initialized clean snapshot through Dependencies.
    from agentdojo.task_suite.load_suites import get_suite
    env = get_suite('v1.2.2', 'workspace').load_and_inject_default_environment({})
    return PtlWall.from_clean_environment(config, env)
