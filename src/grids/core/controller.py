"""Bounded sequential episode loop. The actor only sees messages and schemas."""
import json
from dataclasses import asdict
from grids.core.actions import bind, canonical, digest
from grids.core.audit import AuditFailure, EpisodeAudit
from grids.core.contracts import GateDecision, Outcome
from grids.core.permissions.approvals import ApprovalEvent, pending_record
from grids.core.permissions.bindings import Binding

class Controller:
    def __init__(self, config, actor, wall, gate, facts, approvals, executor, clock, sink, codec, trace=None):
        self.config, self.actor, self.wall, self.gate = config, actor, wall, gate
        self.facts, self.approvals, self.executor = facts, approvals, executor
        self.clock, self.sink, self.codec = clock, sink, codec
        self.trace = trace

    def mediate(self, episode, proposal, action_id, tools, runtime, env, audit):
        if self.trace and self.trace.cancelled():
            return Outcome(False, 'CANCELLED', 'BLOCK', error='PermissionError: cancelled', terminal='cancelled')
        budget = self.config.runtime
        started = self.clock.monotonic()
        try:
            action = bind(proposal, action_id, tools, self.facts, self.wall, env, budget.max_action_chars)
        except Exception:
            audit.emit('validation_failure', reason='INVALID_ACTION', original_id_hash=digest(proposal.call_id))
            return Outcome(False, 'INVALID_ACTION', 'BLOCK', error='PermissionError: invalid tool, arguments, or facts')
        audit.emit('proposed_action', action=action, original_hash=digest(json.loads(action.original_json)),
                   original_id_hash=digest(proposal.original_call_id), evidence_complete=action.evidence_complete)
        if self.trace:
            self.trace('bound_action', {'task': episode.task, 'action': asdict(action)})
        if action_id in self.executor.ledger.outcomes:
            try:
                return self.executor.ledger.replay(episode, action)
            except ValueError:
                return Outcome(False, 'REDELIVERY_BINDING_MISMATCH', 'BLOCK',
                               error='PermissionError: changed action attempt')
        try:
            wall = self.wall.evaluate(action) if episode.mode != 'unprotected' else None
        except Exception:
            return Outcome(False, 'WALL_FAILURE', 'BLOCK', error='PermissionError: wall unavailable')
        if wall is not None:
            if self.trace:
                self.trace('wall', {'action_id': action.action_id, 'verdict': asdict(wall)})
            audit.emit('wall_verdict', action=action, reason=wall.reason, decision=wall.verdict,
                       elapsed_seconds=self.clock.monotonic() - started)
            if wall.verdict != 'PASS':
                return Outcome(False, wall.reason, 'BLOCK', error='PermissionError: ' + wall.reason)

        gate_started = self.clock.monotonic()
        if episode.mode == 'wall_gatekeeper':
            # Preserve exact task and action. Refuse oversized evidence rather than
            # truncate it and incorrectly label the remaining state complete.
            if len(episode.task) + len(action.arguments_json) + len(action.facts_json) > budget.max_gate_chars:
                decision = GateDecision('ASK', 'APPLICATION_CHARACTER_BUDGET',
                    backend='existing_laya',
                    error_kind='application_character_budget')
            else:
                try:
                    decision = self.gate.evaluate(episode, action, wall)
                    if not isinstance(decision, GateDecision) or decision.decision not in ('ALLOW', 'ASK', 'BLOCK'):
                        raise ValueError('MALFORMED_GATE_DECISION')
                except Exception as exc:
                    decision = GateDecision('ASK', 'MODEL_UNAVAILABLE', error_kind=type(exc).__name__)
        else:
            decision = GateDecision('ALLOW', 'EXPLICIT_MODE_BYPASS')
        audit.emit('gate_decision', action=action, **asdict(decision),
                   elapsed_seconds=self.clock.monotonic() - gate_started)
        if self.trace:
            self.trace('decision', {'action_id': action.action_id, 'decision_id': action.action_id + ':decision',
                       'decision': asdict(decision)})
        if decision.decision == 'BLOCK':
            return Outcome(False, decision.reason, 'BLOCK', error='PermissionError: ' + decision.reason)
        # Mandatory confirmation and incomplete evidence are explicit enforcement
        # overrides of ALLOW; they cannot override a semantic BLOCK.
        if wall is not None and (wall.confirmation_required or not action.evidence_complete):
            reason = 'CONFIRMATION_REQUIRED' if wall.confirmation_required else 'INCOMPLETE_EVIDENCE'
            audit.emit('enforcement_override', action=action, reason=reason,
                       decision='ASK', policy_override=True)
            decision = GateDecision('ASK', reason)
        expires = min(episode.deadline, self.clock.monotonic() + budget.authorization_ttl_seconds)
        decision_id = action.action_id + ':decision'
        if decision.decision == 'ASK':
            episode.asks += 1
            pending = pending_record(episode, action, decision.reason, expires,
                decision=asdict(decision), remaining=expires - self.clock.monotonic())
            episode.pending.append(pending)
            if self.trace:
                self.trace('pending_approval', asdict(pending))
            audit.emit('pending_approval', action=action, reason=decision.reason, decision='ASK')
            feedback = self.approvals.request(pending)
            if feedback is None:
                return Outcome(False, decision.reason, 'ASK', error='PermissionError: confirmation required',
                               terminal='pending_approval')
            valid = (isinstance(feedback, ApprovalEvent) and type(feedback.approved) is bool and feedback.pending_id == pending.pending_id and
                     feedback.binding == pending.binding and feedback.binding.matches(episode, action, self.clock.monotonic()))
            if not valid:
                audit.emit('invalid_approval', action=action, reason='INVALID_APPROVAL')
                return Outcome(False, 'INVALID_APPROVAL', 'BLOCK', error='PermissionError: invalid approval')
            audit.emit('approval', action=action, reason='APPROVED' if feedback.approved else 'REJECTED')
            if not feedback.approved:
                return Outcome(False, 'APPROVAL_REJECTED', 'BLOCK', error='PermissionError: approval rejected')
            decision_id = pending.pending_id
        if self.clock.monotonic() >= episode.deadline:
            return Outcome(False, 'EPISODE_DEADLINE', 'CANCELLED', error='Not executed: episode deadline', terminal='budget_exceeded')
        token = self.executor.ledger.issue(Binding.create(episode, action, expires), decision_id)
        return self.executor.execute(token, episode, action, runtime, env, tools, self.facts,
                                     self.wall, self.clock, audit, budget)

    def run(self, episode, runtime, env, messages, tools):
        audit = EpisodeAudit(self.sink, episode, self.clock)
        history = list(messages or [])
        budget = self.config.runtime
        open_calls = []
        try:
            audit.emit('episode_started', content_hash=digest(episode.task))
            history = self.codec.initialize(episode.task, history, episode)
            for turn in range(budget.max_actor_turns):
                if self.trace and getattr(self.trace, 'cancelled', lambda: False)():
                    episode.terminal = 'cancelled'
                    break
                remaining = episode.deadline - self.clock.monotonic()
                if remaining <= 0:
                    episode.terminal = 'budget_exceeded'
                    break
                actor_messages = self.codec.to_actor(history)
                schemas = tools.schemas()
                context_size = len(canonical({'messages': actor_messages, 'tools': schemas}))
                if context_size > budget.max_context_chars:
                    audit.emit('budget_exceeded', reason='CONTEXT_BUDGET', evidence_complete=False,
                               omitted_chars=0)
                    episode.terminal = 'budget_exceeded'
                    break
                audit.emit('actor_request', count=len(actor_messages))
                actor_started = self.clock.monotonic()
                reply = self.actor.respond(actor_messages, schemas, remaining)
                if self.trace:
                    self.trace('proposal_batch', {'turn': turn, 'task': episode.task, 'response': reply,
                        'messages': actor_messages, 'environment': env.model_dump(mode='json'), 'schemas': schemas})
                assistant, proposals = self.codec.from_actor(reply, episode, turn)
                history.append(assistant)
                open_calls = list(assistant['tool_calls'] or [])
                audit.emit('actor_response', count=len(proposals), elapsed_seconds=self.clock.monotonic() - actor_started)
                if not proposals:
                    episode.terminal = 'completed' if self.clock.monotonic() < episode.deadline else 'budget_exceeded'
                    break
                cancel = False
                for offset, (proposal, call) in enumerate(zip(proposals, assistant['tool_calls'])):
                    if self.trace:
                        self.trace('proposal_context', {'turn': turn, 'offset': offset,
                            'messages': self.codec.to_actor(history), 'environment': env.model_dump(mode='json'),
                            'dispatch_eligible': not cancel and episode.calls < budget.max_tool_calls
                                and self.clock.monotonic() < episode.deadline})
                    if cancel:
                        episode.cancelled += 1
                        outcome = Outcome(False, 'BATCH_CANCELLED', 'CANCELLED',
                                          error='Not executed: an earlier batch action was denied, pending, or failed')
                        audit.emit('cancelled_action', reason='BATCH_CANCELLED', original_id_hash=digest(call.id))
                    elif episode.calls >= budget.max_tool_calls or self.clock.monotonic() >= episode.deadline:
                        episode.cancelled += 1
                        outcome = Outcome(False, 'ACTION_BUDGET', 'CANCELLED',
                                          error='Not executed: configured limit', terminal='budget_exceeded')
                    else:
                        episode.calls += 1
                        action_id = f'{episode.episode_id}:{turn}:{offset}'
                        outcome = self.mediate(episode, proposal, action_id, tools, runtime, env, audit)
                    try:
                        result = self.codec.result(call, outcome)
                    except Exception:
                        # Formatting can fail AFTER a real dispatch. Close the call
                        # truthfully without replaying it or discarding later IDs.
                        result = {'role': 'tool', 'tool_call': call, 'tool_call_id': call.id,
                                  'content': [], 'error': 'Tool result formatting failed; execution status is in the audit'}
                        episode.terminal = 'infrastructure_error'
                    history.append(result)
                    open_calls.pop(0)
                    if outcome.terminal:
                        episode.terminal = outcome.terminal
                    if outcome.decision in ('BLOCK', 'ASK'):
                        episode.denials += 1
                        key = digest({'tool': proposal.tool, 'arguments': proposal.arguments})
                        episode.identical_denials[key] = episode.identical_denials.get(key, 0) + 1
                        if episode.terminal == 'running' and (episode.denials >= budget.max_denials or
                                episode.identical_denials[key] >= budget.max_identical_denials):
                            episode.terminal = 'budget_exceeded'
                            audit.emit('budget_exceeded', reason='REPEATED_OR_TOTAL_DENIAL_LIMIT')
                    cancel = cancel or outcome.decision != 'ALLOW' or episode.terminal != 'running'
                if episode.terminal != 'running':
                    break
            else:
                episode.terminal = 'budget_exceeded'
        except Exception as exc:
            episode.error_context = exc
            episode.terminal = 'infrastructure_error'
            # No raw exception strings: provider errors can contain credentials or
            # request payloads. Exception class and safe category suffice by default.
            try:
                audit.emit('infrastructure_failure', reason='EPISODE_FAILURE', error_kind=type(exc).__name__)
            except AuditFailure:
                pass
        # Every published native call receives a correlated result, including when
        # an audit sink or a trusted dependency failed in the middle of a batch.
        for call in open_calls:
            history.append({'role': 'tool', 'tool_call': call, 'tool_call_id': call.id,
                            'content': [], 'error': 'Not executed: episode interrupted before dispatch'})
        if episode.terminal != 'completed':
            history.append(self.codec.terminal(episode.terminal))
        try:
            audit.emit('episode_finished', terminal=episode.terminal, count=episode.executed)
        except AuditFailure:
            episode.terminal = 'infrastructure_error'
            history.append(self.codec.terminal(episode.terminal))
        return history
