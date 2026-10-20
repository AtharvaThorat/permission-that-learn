"""One writer per attempt; atomic final publication and content checksums."""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4
from pydantic import Field
from blackbox.config import Strict


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(uuid4().hex[:12] + '.tmp')
    with tmp.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


def checksum(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def lines(path):
    if not Path(path).exists():
        return []
    result = []
    rows = Path(path).read_text(encoding='utf-8').splitlines()
    for i, line in enumerate(rows):
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError:
            if i != len(rows) - 1:
                raise
    return result


class Result(Strict):
    schema_version: Literal[1] = 1
    run_id: str
    episode_spec_id: str
    attempt_id: str
    pair_id: str
    actor_profile: str
    actor: dict
    mode: str
    identity: dict
    suite: str
    task: str
    attack: dict | None
    repetition: int
    seed: int
    started_at: str
    ended_at: str
    lifecycle: Literal['completed', 'pending_approval', 'budget_exceeded', 'infrastructure_error',
                       'invalid_configuration', 'cancelled', 'interrupted']
    publication: Literal['complete'] = 'complete'
    evaluated: bool = False
    utility: bool | None = None
    attack_success: bool | None = None
    attack_score_meaning: Literal['native_attacker_objective_achieved'] = 'native_attacker_objective_achieved'
    attack_exposed: bool | None = None
    counts: dict
    timings_seconds: dict
    actor_usage: dict | None = None
    actor_usage_coverage: dict
    gate_usage: dict | None = None
    backend_errors: list[str] = Field(default_factory=list)
    artifacts: dict
    checksums: dict


class Writer:
    def __init__(self, directory, cancellation=None):
        self.directory = Path(directory)
        self.cancellation = cancellation
        self.streams = {}

    def append(self, filename, value):
        if filename not in self.streams:
            self.streams[filename] = (self.directory / filename).open('x', encoding='utf-8')
        stream = self.streams[filename]
        stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n')
        stream.flush()

    def __call__(self, event, data):
        self.append('decisions.jsonl', {'schema_version': 1, 'event': event, 'timestamp': now(), **data})

    def cancelled(self):
        return bool(self.cancellation and self.cancellation.is_set())

    def close(self):
        for stream in self.streams.values():
            stream.close()

    def checksums(self):
        self.close()
        return {p.relative_to(self.directory).as_posix(): checksum(p)
                for p in self.directory.rglob('*') if p.is_file() and p.name != 'result.json'}
