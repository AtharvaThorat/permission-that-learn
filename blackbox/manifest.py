"""Run provenance and metric definitions; no fabricated benchmark values."""
import importlib.metadata
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any, Literal
from pydantic import Field
from .actions import digest
from .config import Strict

class RunManifest(Strict):
    schema_version: Literal[1] = 1
    run_id: str
    repository_revision: str
    repository_dirty: bool
    config_hash: str
    configuration: dict[str, Any]
    package_versions: dict[str, str]
    platform: str
    python: str
    gatekeeper_manifest: dict[str, Any]
    policy_hash: str
    metadata_hash: str
    attack_file_hash: str | None
    invocation_hash: str
    pending_behavior: Literal['terminal_no_resume'] = 'terminal_no_resume'
    seeds: dict = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=lambda: [
        'in_process_not_hostile_python_sandbox', 'nested_calls_unsupported',
        'no_persistent_idempotency', 'tool_timeout_cooperative_post_return',
        'no_final_text_disclosure_guarantee', 'laya_uncalibrated', 'reference_wall'])

def package_versions():
    result = {}
    for name in ('agentdojo', 'httpx', 'pydantic', 'laya', 'torch', 'transformers'):
        try:
            result[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            result[name] = 'missing'
    return result

def create_manifest(config, run_id):
    root = Path(__file__).resolve().parents[1]
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=root, text=True).strip())
    raw = config.model_dump()
    return RunManifest(run_id=run_id, repository_revision=revision, repository_dirty=dirty,
        config_hash=digest(raw), configuration=raw, package_versions=package_versions(),
        platform=platform.platform(), python=sys.version,
        gatekeeper_manifest=json.loads((root / 'gatekeeper/model_manifest.json').read_text()),
        policy_hash=digest(Path(config.wall.policy_path).read_text(encoding='utf-8')),
        metadata_hash=digest(Path(config.wall.metadata_path).read_text(encoding='utf-8')),
        attack_file_hash=digest(Path(config.agentdojo.attack_file).read_text(encoding='utf-8')) if config.agentdojo.attack_file else None,
        invocation_hash=digest(sys.argv))
