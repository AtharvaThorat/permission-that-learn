"""Evaluate the same frozen action without actor calls, dispatch, or source mutation."""
from dataclasses import asdict
from pathlib import Path
from typing import Literal
from uuid import uuid4
from time import perf_counter
from pydantic import Field
from grids.core.actions import bind, digest, parse_json
from grids.core.config import Config, GateConfig, Strict, WallConfig
from grids.core.contracts import Proposal
from grids.core.permissions.approvals import exclusive_json
from grids.core.permissions.ptl_adapter import PtlWall
from grids.gatekeeper.policy import Gatekeeper
from grids.gatekeeper.schemas import Request
from grids.runs.artifacts import now
from .dataset import load_dataset

COMPARATORS = ('wall_only', 'laya_only', 'wall_gatekeeper')


class EvaluationConfig(Strict):
    schema_version: Literal[1] = 1
    comparators: list[Literal['wall_only', 'laya_only', 'wall_gatekeeper']] = Field(default_factory=lambda: list(COMPARATORS))
    gatekeeper: GateConfig = Field(default_factory=lambda: GateConfig(input_profile='evidence_v2', max_input_tokens=8192))
    max_context_chars: int = Field(default=100000, gt=0)


def reconstruct(record):
    from agentdojo.task_suite.load_suites import get_suite
    from agentdojo.functions_runtime import FunctionsRuntime
    from grids.benchmarks.agentdojo.runner import verify_distribution
    from grids.benchmarks.agentdojo.context import suite_facts, Metadata
    from grids.benchmarks.agentdojo.suites import NativeIdentityContext
    from grids.benchmarks.agentdojo.tools import NativeTools
    from grids.wall.context import WallContext
    from grids.wall.policy import WallPolicy
    verify_distribution(Config())
    data = record['input']
    suite = get_suite(data['benchmark_version'], data['suite'])
    tools = NativeTools(FunctionsRuntime(suite.tools))
    if digest(tools.schemas()) != digest(data['schemas']):
        raise ValueError('NATIVE_SCHEMA_MISMATCH')
    env = suite.environment_type.model_validate(data['environment'])
    cls = WallContext if data['suite'] == 'workspace' else NativeIdentityContext
    wall = PtlWall(WallConfig.model_validate(data['wall_config']), cls.model_validate(data['trusted_identities']),
                   data['suite'], policy=WallPolicy.model_validate(data['policy']))
    raw = data['raw_call']
    function = raw['function']
    args = parse_json(function['arguments'])
    action = bind(Proposal(str(raw.get('id') or record['record_id']), function['name'], args),
                  record['record_id'], tools, suite_facts(data['suite'], Metadata.model_validate(data['metadata'])),
                  wall, env, 1000000)
    return action, wall


def request_for(record, action, wall=None):
    data = record['input']
    # History is untrusted context, never an additional user authorization.
    history = [{'role': m['role'], 'content': m.get('content'), 'tool_calls': m.get('tool_calls'),
                'name': m.get('name')} for m in data['messages'] if m.get('role') in ('assistant', 'tool')]
    confirmation = 'financial' in action.effects
    from grids.benchmarks.agentdojo.suites import inventory
    from grids.wall.inventory import ToolInventory
    inv = ToolInventory.workspace() if data['suite'] == 'workspace' else inventory(data['suite'])
    tool = inv.tools.get(action.tool)
    if tool:
        confirmation |= tool.capability in data['wall_config'].get('confirm_capabilities', [])
    return Request.model_validate({'schema_version': '0.1', 'request_id': record['record_id'],
        'task_id': record['record_id'], 'user_request': data['user_request'],
        'action': {'action_id': action.action_id, 'tool': action.tool, 'arguments': parse_json(action.arguments_json)},
        'wall': None if wall is None else {'verdict': wall.verdict, 'policy_version': wall.policy_version,
            'evaluated_action_id': action.action_id, 'reason_codes': [wall.reason]},
        'verified_context': {'confirmation_required': confirmation if wall is None else wall.confirmation_required,
            'evidence_complete': action.evidence_complete, 'facts': {'metadata': parse_json(action.facts_json),
                'effects': list(action.effects), 'permission_policy': data['policy'],
                'trusted_identities': data['trusted_identities'], 'untrusted_history': history}}})


def wall_decision(verdict, action):
    if verdict.verdict == 'DENY': return 'BLOCK'
    if verdict.verdict != 'PASS' or verdict.confirmation_required or not action.evidence_complete: return 'ASK'
    return 'ALLOW'


def evaluate(dataset, config, output, *, allow_models=False, backend=None):
    config = EvaluationConfig.model_validate(config)
    if not config.comparators or len(set(config.comparators)) != len(config.comparators):
        raise ValueError('Select unique nonempty comparators')
    needs_laya = any(c != 'wall_only' for c in config.comparators)
    if needs_laya and backend is None and not allow_models:
        raise ValueError('Laya evaluation requires --allow-models and prepared local assets')
    manifest, records = load_dataset(dataset)
    if Path(output).resolve().is_relative_to(Path(dataset).resolve()):
        raise ValueError('Replay output must be outside the immutable source dataset')
    if needs_laya and backend is None:
        import os
        from grids.gatekeeper.laya_adapter import LayaBackend
        from grids.gatekeeper.config import resolve_checkpoint
        if any(os.environ.get(k) != '1' for k in ('HF_HUB_OFFLINE', 'TRANSFORMERS_OFFLINE')):
            raise ValueError('OFFLINE_ENV_REQUIRED')
        backend = LayaBackend(*resolve_checkpoint(), cache_dir=config.gatekeeper.cache_dir,
            timeout=config.gatekeeper.timeout_seconds, load_timeout=config.gatekeeper.load_timeout_seconds,
            max_input_tokens=config.gatekeeper.max_input_tokens, context_profile=config.gatekeeper.input_profile,
            max_context_chars=config.max_context_chars)
    out = Path(output)
    out.mkdir(parents=True, exist_ok=False)
    exclusive_json(out / 'manifest.json', {'schema_version': 1, 'kind': 'offline_action_decision_evaluation',
        'evaluation_id': uuid4().hex, 'dataset_id': manifest['dataset_id'], 'config': config.model_dump(),
        'source_actions_sha256': manifest['actions_sha256'], 'created_at': now()})
    from grids.runs.spec import implementation
    exclusive_json(out / 'implementation.json', implementation())
    from grids.runs.artifacts import Writer
    writer = Writer(out)
    def valid(raw):
        return Request.model_validate(raw), None
    gates = {name: Gatekeeper(backend, request_validator=valid, standalone=name == 'laya_only')
             for name in config.comparators if name != 'wall_only'}
    counts = {'records': len(records), 'evaluated': 0, 'errors': 0}
    try:
        for record in records:
            try:
                action, wall = reconstruct(record)
                reconstruction_error = None
            except (ValueError, KeyError, TypeError) as exc:
                reconstruction_error = type(exc).__name__ + ':invalid_action_or_context'
            for name in config.comparators:
                started = perf_counter()
                row = {'record_id': record['record_id'], 'context_id': record['context_id'], 'comparator': name,
                       'status': 'evaluated', 'decision': None, 'raw_prediction': None, 'wall': None, 'error_kind': None}
                try:
                    if reconstruction_error:
                        row.update(status='unevaluable', error_kind=reconstruction_error)
                    else:
                        row['bound_action'] = asdict(action)
                        verdict = wall.evaluate(action) if name != 'laya_only' else None
                        if verdict:
                            row['wall'] = asdict(verdict)
                        if name == 'wall_only' or (verdict and verdict.verdict != 'PASS'):
                            row.update(decision=wall_decision(verdict, action), path='wall_short_circuit')
                        else:
                            request = request_for(record, action, verdict)
                            decision = gates[name].evaluate(request)
                            diagnostics = asdict(decision)
                            diagnostics['output'] = decision.output.model_dump()
                            row.update(decision=decision.decision, raw_prediction=decision.raw_model_decision,
                                error_kind=decision.error_kind, path=decision.path,
                                status='error' if decision.error or decision.error_kind else 'evaluated',
                                diagnostics=diagnostics, input_sha256=digest(request.model_dump()),
                                permission_input=request.model_dump())
                    counts['evaluated' if row['status'] == 'evaluated' else 'errors'] += 1
                except Exception as exc:
                    row.update(status='error', error_kind=type(exc).__name__, decision=None)
                    counts['errors'] += 1
                row['elapsed_seconds'] = perf_counter() - started
                writer.append('decisions.jsonl', row)
    finally:
        writer.close()
        exclusive_json(out / 'backend.json', {'kind': 'laya' if needs_laya else 'not_used',
            'metadata': getattr(backend, 'metadata', {}),
            'validation': 'injected_test_backend' if backend is not None and not allow_models else 'configured_runtime'})
        if backend is not None: backend.close()
    exclusive_json(out / 'summary.json', counts)
    exclusive_json(out / 'checksums.json', writer.checksums())
    return {'output': str(out), **counts}
