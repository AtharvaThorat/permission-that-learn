"""One native AgentDojo runtime for every experimental condition."""
from dataclasses import asdict
import json
import time
from pathlib import Path
from blackbox.config import Config
from blackbox.contracts import Dependencies
from .artifacts import Writer, Result, atomic, now, lines
from .services import GateLease


def serializable(value):
    return json.loads(json.dumps(value, default=lambda x: x.model_dump(mode='json')))


def execute(spec, services, run_dir, job, attempt, directory, queue_seconds, cancel, *, dependencies=None):
    """dependencies is an explicit CPU fixture seam, never a runtime fallback."""
    started_at, started = now(), time.monotonic()
    writer = Writer(directory, cancel)
    actor = pipeline = None
    utility = attack_success = None
    evaluated = False
    errors = []
    lifecycle = 'infrastructure_error'
    cfg = Config(mode=job['mode'], actor=spec.actors[job['actor_profile']].settings.model_copy(deep=True),
                 gatekeeper=spec.gatekeeper.model_copy(deep=True), runtime=spec.budgets.model_copy(deep=True), wall=spec.wall.model_copy(deep=True))
    cfg.audit.output_directory = str(directory.parent)
    # Native friendly names/caches are never used for reuse; direct suite scoring
    # below and per-attempt unique artifacts are authoritative.
    cfg.agentdojo.user_task_ids = [job['task']]
    cfg.actor.seed = job['seed']
    atomic(directory / 'config.json', cfg.model_dump(mode='json'))
    try:
        from agentdojo.task_suite.load_suites import get_suite
        from agentdojo.logging import LOGGER_STACK
        from integrations.agentdojo.runner import verify_distribution
        from blackbox.permissions.ptl_adapter import PtlWall
        from integrations.agentdojo.context import WorkspaceFacts, Metadata
        from blackbox.factory import build_agentdojo_pipeline
        verify_distribution(cfg)
        suite = get_suite(spec.benchmark_version, spec.suite)
        task = suite.get_user_task_by_id(job['task'])
        attack = job['attack']
        objective = suite.get_injection_task_by_id(attack['objective']) if attack else None
        payloads = attack['payloads'] if attack else {}
        clean = task.init_environment(suite.load_and_inject_default_environment({}))
        wall = PtlWall.from_clean_environment(spec.wall, clean)
        atomic(directory / 'evaluation-only.json', {'user_task': job['task'], 'prompt': task.PROMPT,
               'attack': attack, 'attacker_goal': objective.GOAL if objective else None,
               'native_score_meaning': 'attacker objective achieved when attack present'})
        if dependencies is None:
            actor = services.actor(job['actor_profile'], job['seed'], writer, cancel,
                                   attack.get('marker') if attack else None)
            gate = GateLease(services, writer, cancel) if job['mode'] == 'wall_gatekeeper' else None
            deps = Dependencies(actor=actor, wall=wall, gatekeeper=gate,
                facts=WorkspaceFacts(Metadata.model_validate(spec.metadata)), trace=writer, run_id=attempt)
        else:
            deps = dependencies(job, writer)
            deps.wall = wall
            deps.trace, deps.run_id = writer, attempt
            actor = deps.actor
        with build_agentdojo_pipeline(cfg, deps) as pipeline:
            pipeline.name = 'experiment-' + attempt
            # Native Logger uses a mutable default ContextVar list. A new list
            # per worker prevents log mixing across concurrent episodes.
            token = LOGGER_STACK.set([])
            try:
                if cancel.is_set():
                    lifecycle = 'cancelled'
                else:
                    utility, native_security = suite.run_task_with_pipeline(
                        pipeline, task, objective, payloads)
                    attack_success = native_security if attack else None
                    evaluated = True
                    episode = pipeline.last_episode
                    terminal = episode.terminal if episode else 'infrastructure_error'
                    lifecycle = terminal if terminal in ('completed','pending_approval','budget_exceeded','cancelled') else 'infrastructure_error'
                    if episode and episode.error_context:
                        errors.append(type(episode.error_context).__name__)
            finally:
                LOGGER_STACK.reset(token)
                if pipeline.last_history is not None:
                    atomic(directory / 'conversation.json', serializable(pipeline.last_history))
    except Exception as exc:
        errors.append(type(exc).__name__)
        lifecycle = 'cancelled' if cancel.is_set() else 'infrastructure_error'
    finally:
        writer.close()
    events = lines(directory / 'events.jsonl')
    gates = [e for e in events if e['event'] == 'gate_decision' and e.get('backend') == 'existing_laya']
    records = getattr(actor, 'records', [])
    reported = [r['usage'] for r in records if isinstance(r.get('usage'), dict)]
    usage = {k: sum(r[k] for r in reported if type(r.get(k)) is int)
             for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')
             if any(type(r.get(k)) is int for r in reported)} or None
    errors += [e['error_kind'] for e in events if e.get('error_kind')]
    def count(kind, **matches):
        return sum(e['event'] == kind and all(e.get(k) == v for k,v in matches.items()) for e in events)
    def duration(kind):
        return sum(e.get('elapsed_seconds', 0) for e in events if e['event'] == kind)
    counts = {'actor_requests': count('actor_request'), 'tool_proposals': count('proposed_action') + count('validation_failure'),
        'dispatches': count('execution_result', executed=True), 'wall_denied': sum(
            e['event'] == 'wall_verdict' and e.get('decision') != 'PASS' for e in events),
        'gatekeeper_blocked': sum(e.get('decision') == 'BLOCK' for e in gates),
        'ask': count('pending_approval'), 'cancelled_actions': count('cancelled_action')}
    gate_usage = [e.get('diagnostics') for e in gates if e.get('diagnostics')]
    result = Result(run_id=Path(run_dir).name, episode_spec_id=job['episode_spec_id'],
        attempt_id=attempt, pair_id=job['pair_id'], actor_profile=job['actor_profile'], actor=job['actor'],
        mode=job['mode'], identity=job['identity'], suite=job['suite'], task=job['task'], attack=job['attack'],
        repetition=job['repetition'], seed=job['seed'], started_at=started_at, ended_at=now(),
        lifecycle=lifecycle, evaluated=evaluated, utility=utility, attack_success=attack_success,
        attack_exposed=(getattr(actor, 'exposed', None) if job['attack'] else None),
        counts=counts, timings_seconds={'queue_wait': queue_seconds,
            'actor_request': sum(r['latency_seconds'] for r in records) if records else None,
            'actor_queue': sum(r['queue_seconds'] for r in records) if records else None,
            'gatekeeper': duration('gate_decision'), 'wall_and_facts': duration('wall_verdict'),
            'tool_execution': duration('execution_result'), 'episode_total': time.monotonic() - started},
        actor_usage=usage, actor_usage_coverage={'reported_requests': len(reported), 'requests': counts['actor_requests']},
        gate_usage={'evaluations': gate_usage} if gate_usage else None, backend_errors=sorted(set(errors)),
        artifacts={'configuration': 'config.json', 'events': 'events.jsonl', 'conversation': 'conversation.json',
                   'decisions': 'decisions.jsonl', 'actor': 'actor.jsonl', 'evaluation_only': 'evaluation-only.json'},
        checksums=writer.checksums())
    result.artifacts = {k:v for k,v in result.artifacts.items() if (directory/v).exists()}
    return result.model_dump(mode='json')
