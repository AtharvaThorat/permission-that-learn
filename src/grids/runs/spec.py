"""Versioned specifications and deterministic, offline job expansion."""
import importlib.metadata
import json
import os
from pathlib import Path
from typing import Literal
from pydantic import Field, model_validator
from grids.core.config import Strict, ActorConfig, GateConfig, RuntimeConfig, WallConfig, AGENTDOJO_REVISION
from grids.core.actions import digest

from grids.paths import ROOT, PACKAGE
Mode = Literal['unprotected', 'wall_only', 'wall_gatekeeper']


class ActorProfile(Strict):
    settings: ActorConfig
    resource_group: str
    max_concurrent_requests: int = Field(default=1, ge=1, le=64)
    endpoint_revision_enforced: Literal[False] = False
    provenance_note: str = 'External endpoint identity is user-declared, not verified.'


class Attack(Strict):
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]+$')
    task: str
    objective: str
    payloads: dict[str, str]
    marker: str | None = None
    native_template: Literal['direct', 'ignore_previous', 'system_message', 'injecagent'] | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode='after')
    def nonempty(self):
        if (not self.payloads and self.native_template is None) or any(not v for v in self.payloads.values()):
            raise ValueError('Explicit nonempty fixed payloads required')
        if self.marker and not any(self.marker in text for text in self.payloads.values()):
            raise ValueError('Exposure marker must be in the payload')
        return self


class Limits(Strict):
    global_episodes: int = Field(default=1, ge=1, le=64)
    resource_groups: dict[str, int] = Field(default_factory=lambda: {'gpu0': 1})
    gatekeeper_workers: int = Field(default=1, ge=1, le=8)
    pending_queue: int = Field(default=16, ge=1, le=10000)
    lease_seconds: float = Field(default=120, ge=3)
    sequential_models: bool = True
    run_seconds: float = Field(default=3600, gt=0)


class Specification(Strict):
    schema_version: Literal[1] = 1
    name: str = Field(pattern=r'^[a-zA-Z0-9_-]+$')
    actors: dict[str, ActorProfile]
    modes: list[Mode]
    clean_tasks: list[str] = Field(default_factory=list)
    attacks: list[Attack] = Field(default_factory=list)
    seeds: list[int] = Field(default_factory=lambda: [0])
    repetitions: int = Field(default=1, ge=1, le=10000, exclude_if=lambda value: value == 1)
    budgets: RuntimeConfig = Field(default_factory=RuntimeConfig)
    wall: WallConfig = Field(default_factory=lambda: WallConfig(implementation='ptl'))
    gatekeeper: GateConfig = Field(default_factory=lambda: GateConfig(input_profile='full_evidence'))
    limits: Limits = Field(default_factory=Limits)
    suite: Literal['workspace', 'slack', 'banking'] = 'workspace'
    benchmark_version: Literal['v1.2.2'] = 'v1.2.2'
    agentdojo_revision: Literal[AGENTDOJO_REVISION] = AGENTDOJO_REVISION
    task_panel: str = 'explicit'
    attack_panel: str = 'fixed'
    metadata: dict = Field(default_factory=lambda: {
        'provenance': 'explicit-empty-labels', 'version': '1', 'labels': {}})

    @model_validator(mode='after')
    def matrix(self):
        if not self.actors or not self.modes or not self.seeds or not (self.clean_tasks or self.attacks):
            raise ValueError('Nonempty actor/mode/seed/task selections required')
        for values in (self.modes, self.clean_tasks, self.seeds, [a.id for a in self.attacks]):
            if len(values) != len(set(values)):
                raise ValueError('Duplicate selections: use distinct seeds for intentional repetitions')
        seen = {}
        for key, profile in self.actors.items():
            if not key or profile.resource_group not in self.limits.resource_groups:
                raise ValueError('Every actor needs an explicit resource group')
            # Different served models on one URL must still share a resource cap.
            url = profile.settings.base_url.rstrip('/')
            if url in seen and seen[url] != profile.resource_group:
                raise ValueError('Profiles on one endpoint must share a resource group')
            seen[url] = profile.resource_group
        if any(type(v) is not int or v < 1 for v in self.limits.resource_groups.values()):
            raise ValueError('Positive resource group limits required')
        if self.wall.implementation != 'ptl':
            raise ValueError('Primary experiments require the teammate ptl wall; reference is a legacy fixture')
        if self.gatekeeper.input_profile not in ('full_evidence', 'evidence_v2'):
            raise ValueError('Primary experiments require explicit full gate evidence')
        return self


def load(path):
    return Specification.model_validate_json(Path(path).read_text(encoding='utf-8'))


def implementation():
    files = {}
    for directory in ('src/grids',):
        for p in sorted((ROOT / directory).rglob('*')):
            if p.suffix in ('.py', '.yaml', '.json'):
                files[p.relative_to(ROOT).as_posix()] = digest(p.read_text(encoding='utf-8'))
    return digest(files)


def identities(spec):
    from grids.benchmarks.agentdojo.codec import SYSTEM_PROMPT_VERSION, SYSTEM
    from grids.wall import presets
    from grids.wall.models import Capability
    for capability in spec.wall.confirm_capabilities:
        Capability(capability)
    return {'wall': getattr(presets, spec.wall.ptl_preset).model_dump(mode='json'),
            'wall_config': spec.wall.model_dump(),
            'gatekeeper': spec.gatekeeper.model_dump(),
            'checkpoint': json.loads((PACKAGE / 'gatekeeper/model_manifest.json').read_text(encoding='utf-8'))['baseline'],
            'question_hash': digest((PACKAGE / 'gatekeeper/questions.py').read_text(encoding='utf-8')),
            'actor_system_prompt_version': SYSTEM_PROMPT_VERSION,
            'actor_system_prompt_hash': digest(SYSTEM),
            'implementation': implementation()}


def validate_native(spec):
    """Only schemas, local package metadata and synthetic fixtures; no models."""
    from grids.benchmarks.agentdojo.runner import verify_distribution
    from grids.core.config import Config
    from agentdojo.task_suite.load_suites import get_suite
    verify_distribution(Config())
    suite = get_suite(spec.benchmark_version, spec.suite)
    selected = set(spec.clean_tasks) | {a.task for a in spec.attacks}
    if selected - suite.user_tasks.keys():
        raise ValueError('Unknown native user task')
    defaults = suite.get_injection_vector_defaults()
    native_attacks = {}
    for attack in spec.attacks:
        if attack.objective not in suite.injection_tasks or attack.payloads.keys() - defaults.keys():
            raise ValueError('Unknown native objective/vector')
        suite.get_user_task_by_id(attack.task).init_environment(
            suite.load_and_inject_default_environment(attack.payloads))
        if attack.native_template:
            from agentdojo.attacks import load_attack
            from types import SimpleNamespace
            if attack.native_template not in native_attacks:
                native_attacks[attack.native_template] = load_attack(attack.native_template, suite, SimpleNamespace(name='offline-materialization'))
            expected = native_attacks[attack.native_template].attack(
                suite.get_user_task_by_id(attack.task), suite.get_injection_task_by_id(attack.objective))
            if attack.payloads != expected:
                raise ValueError('Native attack payloads differ from pinned AgentDojo generation')
    identities(spec)
    return suite


def plan(spec, *, native=True):
    if native:
        validate_native(spec)
    identity = identities(spec)
    raw = spec.model_dump(mode='json')
    spec_id = digest(raw)
    jobs = []
    cases = [(task, None) for task in spec.clean_tasks] + [(a.task, a.model_dump()) for a in spec.attacks]
    for actor, profile in sorted(spec.actors.items()):
        for repetition, seed in enumerate(spec.seeds * spec.repetitions):
            for task, attack in cases:
                for mode in spec.modes:
                    behavior = {'actor': profile.model_dump(), 'actor_profile': actor, 'mode': mode,
                        'task': task, 'attack': attack, 'repetition': repetition, 'seed': seed,
                        'budgets': spec.budgets.model_dump(), 'identity': identity,
                        'suite': spec.suite, 'benchmark': spec.benchmark_version,
                        'agentdojo_revision': spec.agentdojo_revision, 'metadata': spec.metadata,
                        'task_panel': spec.task_panel, 'attack_panel': spec.attack_panel}
                    pair = dict(behavior)
                    pair.pop('mode')
                    jobs.append({'episode_spec_id': digest(behavior), 'pair_id': digest(pair),
                                 'spec_id': spec_id, **behavior})
    missing = []
    for key, actor in spec.actors.items():
        if not os.environ.get(actor.settings.api_key_env):
            missing.append(f'{key}:credential_env:{actor.settings.api_key_env}')
    if 'wall_gatekeeper' in spec.modes:
        cache = spec.gatekeeper.cache_dir
        if not cache or not Path(cache).is_dir():
            missing.append('existing_laya_cache')
        try:
            importlib.metadata.version('laya')
        except importlib.metadata.PackageNotFoundError:
            missing.append('laya_runtime_package')
        missing.append('Laya encoder assets and runtime compatibility require later offline runtime verification')
    return {'schema_version': 1, 'spec_id': spec_id, 'identity': identity, 'jobs': jobs,
            'job_count': len(jobs), 'clean_count': sum(j['attack'] is None for j in jobs),
            'attacked_count': sum(j['attack'] is not None for j in jobs),
            'repetitions': len(spec.seeds) * spec.repetitions, 'limits': spec.limits.model_dump(), 'missing_prerequisites': missing,
            'model_breakdown': {k: sum(j['actor_profile'] == k for j in jobs) for k in spec.actors},
            'mode_breakdown': {k: sum(j['mode'] == k for j in jobs) for k in spec.modes},
            'task_breakdown': {k: sum(j['task'] == k for j in jobs) for k in sorted({j['task'] for j in jobs})}}
