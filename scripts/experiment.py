"""Experiment configuration and non-overwriting output/provenance helpers."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def config():
    from gatekeeper.config import checkpoint_config
    settings = checkpoint_config()
    return dict(settings['baseline'], baseline_archive='benchmarks/development')

def new_output_dir(path=None, label='run'):
    path = Path(path) if path is not None else ROOT / 'results' / 'runs' / (
        datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + label)
    path.mkdir(parents=True, exist_ok=False)
    return path

def source_hashes():
    files = list((ROOT / 'gatekeeper').glob('*.py')) + list((ROOT / 'scripts').glob('*.py'))
    files += [ROOT / 'requirements.txt', ROOT / 'gatekeeper/model_manifest.json']
    files.append(ROOT / 'requirements-lock.txt')
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}

def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
