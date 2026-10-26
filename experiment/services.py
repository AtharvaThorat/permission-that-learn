"""Explicit external services and a bounded, persistent, lazy gatekeeper pool."""
from contextlib import contextmanager
from queue import Queue, Empty
import threading
import time
from blackbox.actors.openai_compatible import OpenAICompatibleActor
from blackbox.permissions.gatekeeper_adapter import ExistingLayaGate
from .artifacts import now


class Services:
    def __init__(self, spec):
        self.spec = spec
        self.clients = {}
        self.lock = threading.Lock()
        self.requests = {name: threading.BoundedSemaphore(p.max_concurrent_requests)
                         for name, p in spec.actors.items()}
        self.gates = Queue(maxsize=spec.limits.gatekeeper_workers)
        for _ in range(spec.limits.gatekeeper_workers):
            self.gates.put(ExistingLayaGate(spec.gatekeeper, spec.budgets.max_gate_chars))

    def actor(self, name, seed, writer, cancel, marker=None):
        with self.lock:
            if name not in self.clients:
                import httpx
                self.clients[name] = httpx.Client(follow_redirects=False, trust_env=False)
        config = self.spec.actors[name].settings.model_copy(update={'seed': seed})
        actor = OpenAICompatibleActor(config)
        actor.client = self.clients[name]
        return RecordingActor(actor, self.requests[name], writer, cancel, marker)

    @contextmanager
    def gate(self, cancel):
        while True:
            if cancel.is_set():
                raise RuntimeError('CANCELLED')
            try:
                gate = self.gates.get(timeout=0.1)
                break
            except Empty:
                continue
        try:
            yield gate
        finally:
            gate.recorder = None
            self.gates.put(gate)

    def close(self):
        for client in self.clients.values():
            client.close()
        while not self.gates.empty():
            self.gates.get_nowait().close()


class RecordingActor:
    def __init__(self, actor, semaphore, writer, cancel, marker=None):
        self.actor, self.semaphore, self.writer, self.cancel = actor, semaphore, writer, cancel
        self.marker = marker
        self.records = []
        self.exposed = False

    def respond(self, messages, tools, timeout):
        started = time.monotonic()
        while not self.semaphore.acquire(timeout=min(0.1, timeout)):
            if self.cancel.is_set() or time.monotonic() - started >= timeout:
                raise TimeoutError('ACTOR_QUEUE_DEADLINE')
        acquired = time.monotonic()
        record = {'messages': messages, 'tools': tools, 'queue_seconds': acquired - started,
                  'response': None, 'usage': None, 'error': None}
        try:
            if self.cancel.is_set():
                raise RuntimeError('CANCELLED')
            self.exposed |= bool(self.marker and any(m.get('role') == 'tool'
                                and self.marker in (m.get('content') or '') for m in messages))
            self.writer.append('actor.jsonl', {'event': 'request', 'timestamp': now(),
                                              'messages': messages, 'tools': tools})
            response = self.actor.respond(messages, tools, max(0.001, timeout - (acquired - started)))
            record['response'] = response
            record.update(self.actor.last_metadata)
            return response
        except Exception as exc:
            record['error'] = type(exc).__name__
            raise
        finally:
            record['latency_seconds'] = time.monotonic() - acquired
            self.records.append(record)
            try:
                self.writer.append('actor.jsonl', {'event': 'response', 'timestamp': now(), **record})
            finally:
                self.semaphore.release()

    def close(self):
        # The registry owns the pooled connection.
        pass


class GateLease:
    def __init__(self, services, writer, cancel):
        self.services, self.writer, self.cancel = services, writer, cancel
        self.runtime = None

    def set_native_schemas(self, runtime):
        self.runtime = runtime

    def evaluate(self, episode, action, wall):
        with self.services.gate(self.cancel) as gate:
            gate.set_native_schemas(self.runtime)
            gate.recorder = self.writer
            return gate.evaluate(episode, action, wall)

    def close(self):
        pass
