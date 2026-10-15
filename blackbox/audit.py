"""Default events contain hashes and fixed categories, never argument/body text."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

class AuditFailure(RuntimeError):
    pass

class JsonlAudit:
    def __init__(self, path):
        self.path = Path(path)
        self.stream = None

    def emit(self, event):
        try:
            if self.stream is None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.stream = self.path.open('x', encoding='utf-8')
            self.stream.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + '\n')
            self.stream.flush()
            os.fsync(self.stream.fileno())
        except Exception as exc:
            raise AuditFailure('AUDIT_WRITE_FAILED') from exc

    def close(self):
        if self.stream is not None:
            self.stream.close()

class MemoryAudit:
    """Explicit test sink."""
    def __init__(self):
        self.events = []

    def emit(self, event):
        self.events.append(event)

    def close(self):
        pass

class EpisodeAudit:
    def __init__(self, sink, episode, clock):
        self.sink, self.episode, self.clock = sink, episode, clock

    def emit(self, event_type, *, action=None, reason='NONE', executed=False, **fields):
        allowed = {'elapsed_seconds', 'error_kind', 'decision', 'raw_recommendation',
                   'probabilities', 'backend', 'checkpoint', 'revision', 'prompt_version',
                   'calibration', 'count', 'terminal', 'content_hash', 'original_hash',
                   'evidence_complete', 'omitted_chars', 'original_id_hash', 'policy_override',
                   'decision_id_hash', 'authorization_id_hash', 'expires_at_monotonic'}
        if set(fields) - allowed:
            raise AuditFailure('UNSAFE_AUDIT_FIELDS')
        episode = self.episode
        episode.sequence += 1
        record = {'schema_version': 1, 'event': event_type, 'sequence': episode.sequence,
                  'timestamp': datetime.now(timezone.utc).isoformat(),
                  'monotonic_seconds': self.clock.monotonic() - episode.started,
                  'run_id': episode.run_id, 'episode_id': episode.episode_id,
                  'attempt_id': episode.attempt_id, 'mode': episode.mode,
                  'policy_version': action.policy_version if action else episode.policy_version,
                  'action_id': action.action_id if action else None,
                  'tool': action.tool if action else None,
                  'call_id': action.call_id if action else None,
                  'action_digest': action.digest if action else None,
                  'state_version': action.state_version if action else None,
                  'schema_digest': action.schema_digest if action else None,
                  'executed': executed, 'reason_code': reason, 'redacted': True, **fields}
        try:
            self.sink.emit(record)
        except Exception as exc:
            raise AuditFailure('AUDIT_WRITE_FAILED') from exc
