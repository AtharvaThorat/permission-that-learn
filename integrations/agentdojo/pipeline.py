from pathlib import Path
from uuid import uuid4
from agentdojo.agent_pipeline.base_pipeline_element import BasePipelineElement
from blackbox.actors.openai_compatible import OpenAICompatibleActor
from blackbox.audit import JsonlAudit
from blackbox.controller import Controller
from blackbox.execution import GuardedExecutor
from blackbox.permissions.approvals import PendingApprovalProvider
from blackbox.permissions.gatekeeper_adapter import ExistingLayaGate
from blackbox.permissions.rules import RulesGate
from blackbox.permissions.wall import ReferenceWall
from blackbox.state import Clock, Episode
from .codec import NativeCodec
from .context import WorkspaceFacts
from .tools import NativeTools

class UnprotectedFacts:
    """Explicit simulation comparator; no permission metadata restricts dispatch."""
    def resolve(self, tool, arguments, env):
        return {'source': 'unprotected_comparison', 'missing': []}

class GuardedAgentDojoPipeline(BasePipelineElement):
    def __init__(self, config, dependencies):
        self.config, self.dependencies = config, dependencies
        self.name = 'blackbox-' + config.mode
        self.run_id = dependencies.run_id or uuid4().hex
        self.actor = dependencies.actor if dependencies.actor is not None else OpenAICompatibleActor(config.actor)
        from blackbox.permissions.ptl_adapter import build_wall
        self.wall = dependencies.wall if dependencies.wall is not None else build_wall(config.wall)
        self.facts = dependencies.facts if dependencies.facts is not None else (
            UnprotectedFacts() if config.mode == 'unprotected' else WorkspaceFacts.from_file(config.wall.metadata_path))
        self.gate = dependencies.gatekeeper if dependencies.gatekeeper is not None else (
            ExistingLayaGate(config.gatekeeper, config.runtime.max_gate_chars) if config.mode == 'wall_gatekeeper' else RulesGate())
        self.approvals = dependencies.approvals if dependencies.approvals is not None else PendingApprovalProvider()
        self.clock = dependencies.clock if dependencies.clock is not None else Clock()
        self.audit = dependencies.audit if dependencies.audit is not None else JsonlAudit(
            Path(config.audit.output_directory) / self.run_id / 'events.jsonl')
        self.metadata = {k: v for k, v in dependencies.metadata.items() if k in ('suite', 'task_id', 'injection_task_id')}
        self.last_episode = None
        self.last_history = None
        self.closed = False

    def query(self, query, runtime, env=None, messages=None, extra_args=None):
        if self.closed:
            raise RuntimeError('PIPELINE_CLOSED')
        if not isinstance(query, str) or not query.strip() or env is None:
            raise ValueError('A nonempty authentic task and supplied environment are required')
        now = self.clock.monotonic()
        episode = Episode(self.run_id, query, self.config.mode, self.wall.version, now,
                          now + self.config.runtime.max_episode_seconds, dict(self.metadata))
        # Authorization state is fresh for every top-level query. No prompt-based
        # resume or ledger reuse; real persistence/continuation is deferred.
        executor = self.dependencies.executor if self.dependencies.executor is not None else GuardedExecutor()
        if hasattr(self.gate, 'set_native_schemas'):
            self.gate.set_native_schemas(runtime)
        if self.dependencies.trace:
            self.dependencies.trace('environment_initial', {'state': env.model_dump(mode='json')})
        controller = Controller(self.config, self.actor, self.wall, self.gate, self.facts,
                                self.approvals, executor, self.clock, self.audit, NativeCodec(), self.dependencies.trace)
        history = controller.run(episode, runtime, env, messages, NativeTools(runtime, self.config.mode != 'unprotected'))
        self.last_episode = episode
        self.last_history = history
        if self.dependencies.trace:
            self.dependencies.trace('environment_final', {'state': env.model_dump(mode='json')})
        if self.config.audit.record_raw_content:
            from agentdojo.logging import Logger
            try:
                Logger.get().log(history)
            except Exception as exc:
                episode.error_context = exc
                episode.terminal = 'infrastructure_error'
                history.append(NativeCodec().terminal(episode.terminal))
        # Framework metadata returns to the caller without entering either model.
        return query, runtime, env, history, extra_args if extra_args is not None else {}

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.actor.close()
        finally:
            try:
                self.gate.close()
            finally:
                if hasattr(self.audit, 'close'):
                    self.audit.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
