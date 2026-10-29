"""The sole native runtime dispatch location, shared by all comparison modes."""
import json
from grids.core.actions import bind, digest
from grids.core.audit import AuditFailure
from grids.core.contracts import Outcome, Proposal
from grids.core.permissions.bindings import AuthorizationLedger


def _expected_read_only_error(action, error):
    """Recognize native lookup misses without treating writes as recoverable."""
    return (
        bool(error)
        and action.effects == ('read',)
        and isinstance(error, str)
        and error.startswith('ValueError:')
    )


class GuardedExecutor:
    def __init__(self, ledger=None):
        self.ledger = ledger if ledger is not None else AuthorizationLedger()

    def execute(self, token, episode, action, runtime, env, tools, facts, wall, clock, audit, budgets):
        if action.action_id in self.ledger.outcomes:
            try:
                return self.ledger.replay(episode, action)
            except ValueError:
                return Outcome(False, 'REDELIVERY_BINDING_MISMATCH', 'BLOCK',
                               error='PermissionError: changed action attempt')
        started = clock.monotonic()
        try:
            if started >= episode.deadline:
                raise ValueError('EPISODE_DEADLINE')
            proposal = Proposal(action.call_id, action.tool, json.loads(action.arguments_json))
            fresh = bind(proposal, action.action_id, tools, facts, wall, env, budgets.max_action_chars)
            if (fresh.digest, fresh.state_version, fresh.policy_version, fresh.schema_digest) != (
                    action.digest, action.state_version, action.policy_version, action.schema_digest):
                raise ValueError('STALE_BINDING_REEVALUATION_REQUIRED')
            if episode.mode != 'unprotected' and wall.evaluate(fresh).verdict != 'PASS':
                raise ValueError('WALL_RECHECK_FAILED')
            # Rechecking before audit and consumption fails closed. Trusted audit
            # sinks must not mutate policy/environment (in-process boundary).
            audit.emit('execution_authorization', action=action, reason='BOUND_ALLOW',
                       decision_id_hash=digest(self.ledger._entries[token].decision_id),
                       authorization_id_hash=digest(token),
                       expires_at_monotonic=self.ledger._entries[token].binding.expires,
                       elapsed_seconds=clock.monotonic() - started)
            authorization = self.ledger.consume(token, episode, fresh, clock.monotonic())
            audit.emit('dispatch', action=action, reason='DISPATCH_ATTEMPT', executed=False)
            if clock.monotonic() >= episode.deadline or not authorization.binding.matches(episode, fresh, clock.monotonic()):
                raise ValueError('AUTHORIZATION_EXPIRED_DURING_AUDIT')
        except Exception as exc:
            episode.error_context = exc
            try:
                audit.emit('authorization_rejected', action=action, reason='AUTHORIZATION_REJECTED',
                           error_kind=type(exc).__name__)
            except AuditFailure:
                pass
            outcome = Outcome(False, 'AUTHORIZATION_REJECTED', 'BLOCK',
                              error='PermissionError: authorization invalid or stale',
                              terminal='infrastructure_error' if isinstance(exc, AuditFailure) else None)
            self.ledger.outcomes[action.action_id] = outcome
            return outcome

        # Consume BEFORE invoking: even an exception may follow a side effect.
        dispatch_started = clock.monotonic()
        try:
            result, error = runtime.run_function(env, action.tool, json.loads(action.arguments_json))
            elapsed = clock.monotonic() - dispatch_started
            timeout = elapsed > budgets.tool_timeout_seconds or clock.monotonic() >= episode.deadline
            expected_error = _expected_read_only_error(action, error)
            outcome = Outcome(
                True,
                'TOOL_TIMEOUT_UNCERTAIN' if timeout else (
                    'READ_ONLY_TOOL_ERROR' if expected_error else ('TOOL_ERROR' if error else 'EXECUTED')),
                'ALLOW',
                result,
                error,
                'uncertain_execution' if timeout or (error and not expected_error) else None)
        except Exception as exc:
            episode.error_context = exc
            expected_error = isinstance(exc, ValueError) and action.effects == ('read',)
            outcome = Outcome(
                True,
                'READ_ONLY_TOOL_ERROR' if expected_error else 'TOOL_EXCEPTION_UNCERTAIN',
                'ALLOW',
                error='ToolError: read-only lookup failed' if expected_error
                else 'ToolError: execution raised; side effects may have occurred',
                terminal=None if expected_error else 'uncertain_execution')
        episode.executed += 1
        self.ledger.outcomes[action.action_id] = outcome
        try:
            audit.emit('execution_result', action=action, reason=outcome.reason, executed=True,
                       elapsed_seconds=clock.monotonic() - dispatch_started,
                       error_kind='native_tool_error' if outcome.error else None)
        except AuditFailure:
            # Preserve the result in memory; never repeat dispatch to recover a log.
            outcome = Outcome(True, 'POST_DISPATCH_AUDIT_FAILURE', 'ALLOW', outcome.result,
                              outcome.error, 'infrastructure_error')
            self.ledger.outcomes[action.action_id] = outcome
        return outcome
