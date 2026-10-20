"""Strict JSON configuration. Readiness is separate from parsing."""
import json
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from pydantic import BaseModel, ConfigDict, Field, model_validator

AGENTDOJO_REVISION = '089ed468cf3ed0322acc66b0211f26d9d90dbf60'

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)

class ActorConfig(Strict):
    backend: Literal['openai_compatible'] = 'openai_compatible'
    model_id: str = Field(default='Qwen/Qwen3-8B', min_length=1)
    served_model_name: str = Field(default='Qwen3-8B', min_length=1)
    model_revision: str | None = None
    local_model_path: str | None = None
    template_provenance: str | None = None
    server_version: str | None = None
    quantization: str | None = None
    base_url: str = 'http://127.0.0.1:8000/v1'
    api_key_env: str = Field(default='BLACKBOX_ACTOR_API_KEY', pattern=r'^[A-Za-z_][A-Za-z0-9_]*$')
    timeout_seconds: float = Field(default=120.0, gt=0)
    max_retries: int = Field(default=1, ge=0, le=3)
    temperature: float = Field(default=0.7, ge=0, le=2)
    top_p: float = Field(default=0.8, gt=0, le=1)
    max_output_tokens: int = Field(default=2048, gt=0)
    max_response_bytes: int = Field(default=1048576, gt=0)
    thinking_enabled: bool | None = False
    stream: Literal[False] = False
    provider: Literal['vllm_qwen3', 'openai_compatible'] = 'vllm_qwen3'
    dtype: str | None = None
    context_limit: int = Field(default=8192, gt=0)
    seed: int | None = None

    @model_validator(mode='after')
    def endpoint(self):
        url = urlsplit(self.base_url)
        if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError('Explicit HTTP(S) endpoint required; credentials/query strings are forbidden')
        if self.model_revision is not None and (len(self.model_revision) != 40 or any(c not in '0123456789abcdef' for c in self.model_revision)):
            raise ValueError('Actor revision must be an exact commit or null (unresolved)')
        return self

class GateConfig(Strict):
    backend: Literal['existing_laya'] = 'existing_laya'
    profile: Literal['original_single'] = 'original_single'
    cache_dir: str | None = None
    timeout_seconds: float = Field(default=30.0, gt=0)
    load_timeout_seconds: float = Field(default=300.0, gt=0)
    allow_downloads: Literal[False] = False
    device: Literal['cpu'] = 'cpu'
    input_profile: Literal['legacy_collection_summary', 'full_evidence'] = 'legacy_collection_summary'

class RuntimeConfig(Strict):
    max_actor_turns: int = Field(default=15, gt=0)
    max_tool_calls: int = Field(default=30, gt=0)
    max_denials: int = Field(default=10, gt=0)
    max_identical_denials: int = Field(default=2, gt=0)
    max_episode_seconds: float = Field(default=600.0, gt=0)
    tool_timeout_seconds: float = Field(default=30.0, gt=0)
    max_context_chars: int = Field(default=100000, gt=0)
    max_gate_chars: int = Field(default=24000, gt=0)
    max_action_chars: int = Field(default=32000, gt=0)
    authorization_ttl_seconds: float = Field(default=300.0, gt=0)
    execute_calls_sequentially: Literal[True] = True
    reject_nested_calls: Literal[True] = True
    cancel_remaining_batch_on_nonallow: Literal[True] = True

class BenchmarkConfig(Strict):
    suite: Literal['workspace'] = 'workspace'
    distribution_version: Literal['0.1.35'] = '0.1.35'
    source_revision: Literal[AGENTDOJO_REVISION] = AGENTDOJO_REVISION
    benchmark_version: Literal['v1.2.2'] = 'v1.2.2'
    user_task_ids: list[str] = Field(default_factory=list)
    injection_task_ids: list[str] = Field(default_factory=list)
    attack_name: Literal['fixed_file'] | None = None
    attack_file: str | None = None
    allow_all_tasks: Literal[False] = False
    allow_all_injection_tasks: Literal[False] = False

    @model_validator(mode='after')
    def attack(self):
        if self.attack_name and (not self.injection_task_ids or not self.attack_file):
            raise ValueError('Attacked runs require explicit injection IDs and a fixed injection file')
        if not self.attack_name and (self.injection_task_ids or self.attack_file):
            raise ValueError('Clean configuration cannot contain attack selection')
        for values in (self.user_task_ids, self.injection_task_ids):
            if len(values) != len(set(values)) or any(not v.strip() for v in values):
                raise ValueError('Task IDs must be unique and nonempty')
        return self

class WallConfig(Strict):
    implementation: Literal['reference', 'ptl'] = 'reference'
    ptl_preset: Literal['STRICT_WORKSPACE', 'WORKSPACE_RELAXED'] = 'STRICT_WORKSPACE'
    confirm_capabilities: list[str] = Field(default_factory=list)
    policy_path: str = Field(default_factory=lambda: str(Path(__file__).resolve().parents[1] / 'configs/blackbox/policies/workspace_example.json'))
    metadata_path: str = Field(default_factory=lambda: str(Path(__file__).resolve().parents[1] / 'configs/blackbox/policies/workspace_metadata.json'))

class AuditConfig(Strict):
    output_directory: str = 'results/blackbox'
    record_raw_content: bool = False

class Config(Strict):
    schema_version: Literal[1] = 1
    mode: Literal['unprotected', 'wall_only', 'wall_gatekeeper', 'wall_rules'] = 'wall_gatekeeper'
    simulation_only: Literal[True] = True
    learning_enabled: Literal[False] = False
    approval_provider: Literal['pending'] = 'pending'
    actor: ActorConfig = Field(default_factory=ActorConfig)
    gatekeeper: GateConfig = Field(default_factory=GateConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    agentdojo: BenchmarkConfig = Field(default_factory=BenchmarkConfig)
    wall: WallConfig = Field(default_factory=WallConfig)
    audit: AuditConfig = Field(default_factory=AuditConfig)

    def require_selection(self):
        if not self.agentdojo.user_task_ids:
            raise ValueError('No user tasks selected; empty selection never means all tasks')

def load_config(path):
    path = Path(path).resolve()
    config = Config.model_validate(json.loads(path.read_text(encoding='utf-8-sig')))
    # Only configuration resources are relative to the config file. Output/assets
    # remain explicit user paths relative to the invoking working directory.
    for name in ('policy_path', 'metadata_path'):
        value = getattr(config.wall, name)
        setattr(config.wall, name, str((path.parent / value).resolve()))
    if config.agentdojo.attack_file:
        config.agentdojo.attack_file = str((path.parent / config.agentdojo.attack_file).resolve())
    return config
