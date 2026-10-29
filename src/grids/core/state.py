import time
from dataclasses import dataclass, field
from uuid import uuid4

class Clock:
    def monotonic(self):
        return time.monotonic()

@dataclass
class Episode:
    run_id: str
    task: str
    mode: str
    policy_version: str
    started: float
    deadline: float
    metadata: dict = field(default_factory=dict)
    schema_version: int = 1
    episode_id: str = field(default_factory=lambda: uuid4().hex)
    attempt_id: str = field(default_factory=lambda: uuid4().hex)
    environment_id: str = field(default_factory=lambda: uuid4().hex)
    provenance: str = 'native_query_argument'
    terminal: str = 'running'
    calls: int = 0
    denials: int = 0
    identical_denials: dict = field(default_factory=dict)
    seen_call_ids: set = field(default_factory=set)
    sequence: int = 0
    executed: int = 0
    asks: int = 0
    cancelled: int = 0
    pending: list = field(default_factory=list)
    error_context: object = field(default=None, repr=False)
