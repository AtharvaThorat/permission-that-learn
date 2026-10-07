"""Real spawned IPC with a fake worker; no model imports or network."""
import json
import multiprocessing as mp
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from gatekeeper import Gatekeeper, GateDecision, Request, LayaBackend
from gatekeeper.config import resolve_checkpoint
from gatekeeper.laya_adapter import parse_response
from tests.test_gatekeeper import request, response, MockBackend
from tests.test_question_design import decomposed_response


def fake_worker(pipe, checkpoint, revision, cache, mode):
    if mode == 'never_ready':
        time.sleep(30)
        return
    pipe.send({'ready': True, 'actual_checkpoint': checkpoint, 'revision': revision,
               'device': 'cuda' if mode == 'wrong_device' else 'cpu', 'config': {}})
    count = 0
    while True:
        state = pipe.recv()
        if state is None:
            break
        if mode == 'hang':
            time.sleep(30)
            continue
        count += 1
        raw = response()
        raw.update(worker_pid=os.getpid(), worker_calls=count)
        pipe.send({'raw': raw, 'api_calls': 1})
    pipe.close()


class LifecycleTests(unittest.TestCase):
    def context(self, mode='single'):
        context = mp.get_context('spawn')
        def process(**kwargs):
            args = list(kwargs['args'])
            args[-1] = mode
            return context.Process(target=fake_worker, args=tuple(args), daemon=True)
        return patch('gatekeeper.laya_adapter.mp.get_context', return_value=SimpleNamespace(
            Pipe=context.Pipe, Process=process))

    def test_persistent_reuse_and_graceful_idempotent_shutdown(self):
        with self.context(), patch('gatekeeper.laya_adapter.importlib.util.find_spec', return_value=object()):
            backend = LayaBackend(load_timeout=10)
            with backend:
                worker = backend.process
                backend.initialize()
                a = backend.predict(Request.model_validate(request()))
                b = backend.predict(Request.model_validate(request()))
                self.assertIsNone(a.error)
                self.assertEqual(a.raw['worker_pid'], b.raw['worker_pid'])
                self.assertEqual((a.raw['worker_calls'], b.raw['worker_calls']), (2, 3))
                self.assertGreater(backend.metadata['initialization_seconds'], 0)
                self.assertGreater(backend.metadata['first_inference_seconds'], 0)
            self.assertFalse(worker.is_alive())
            self.assertEqual(worker.exitcode, 0)
            backend.close()
            self.assertEqual(backend.predict(Request.model_validate(request())).error_kind, 'closed')

    def test_timeout_and_device_mismatch_fail_closed(self):
        for mode, kind in [('never_ready', 'initialization_timeout'), ('hang', 'inference_timeout'),
                           ('wrong_device', 'download_or_load_failure')]:
            with self.subTest(mode=mode), self.context(mode), patch(
                    'gatekeeper.laya_adapter.importlib.util.find_spec', return_value=object()):
                backend = LayaBackend(load_timeout=0.05 if mode == 'never_ready' else 10, timeout=0.05)
                try:
                    result = Gatekeeper(backend).evaluate(request())
                    self.assertEqual(result.decision, 'ASK')
                    self.assertEqual(result.error_kind, kind)
                    self.assertIsNone(backend.process)
                finally:
                    backend.close()

    def test_initialization_and_inference_failure_categories(self):
        with patch('gatekeeper.laya_adapter.importlib.util.find_spec', return_value=None):
            backend = LayaBackend()
            result = Gatekeeper(backend).evaluate(request())
            self.assertEqual(result.error_kind, 'download_or_load_failure')
            self.assertEqual(result.decision, 'ASK')
        backend = LayaBackend()
        backend.initialized = True
        backend.process = SimpleNamespace(is_alive=lambda: True)
        backend.pipe = SimpleNamespace(send=lambda state: None, poll=lambda timeout: True,
            recv=lambda: {'error': 'synthetic forward failure', 'api_calls': 1})
        result = backend.predict(Request.model_validate(request()))
        self.assertEqual(result.error_kind, 'inference_failure')
        self.assertIsNone(result.decision)

    def test_spawn_failure_is_reported_and_pipe_closed(self):
        from unittest.mock import Mock
        pipe, child = Mock(), Mock()
        process = Mock()
        process.start.side_effect = OSError('synthetic spawn failure')
        process.is_alive.return_value = False
        process.join.side_effect = AssertionError('not started')
        context = SimpleNamespace(Pipe=lambda: (pipe, child), Process=lambda **kwargs: process)
        with patch('gatekeeper.laya_adapter.mp.get_context', return_value=context), patch(
                'gatekeeper.laya_adapter.importlib.util.find_spec', return_value=object()):
            backend = LayaBackend()
            backend.initialize()
        self.assertEqual(backend.error_kind, 'download_or_load_failure')
        self.assertIn('synthetic spawn failure', backend.error)
        child.close.assert_called_once()
        pipe.close.assert_called_once()
        self.assertIsNone(backend.process)

    def test_default_pins_cache_and_timeout_validation(self):
        backend = LayaBackend()
        self.assertEqual((backend.checkpoint, backend.revision), resolve_checkpoint(profile='baseline'))
        with patch.dict(os.environ, {'LAYA_CACHE_DIR': 'tmp/test-cache'}):
            self.assertEqual(LayaBackend().cache_dir, str(Path('tmp/test-cache').resolve()))
        for value in (0, -1, float('inf'), float('nan'), True):
            for field in ('timeout', 'load_timeout'):
                with self.assertRaises(ValueError):
                    LayaBackend(**{field: value})


class PublicInterfaceTests(unittest.TestCase):
    def test_typed_request_preserves_ids(self):
        result = Gatekeeper(MockBackend()).evaluate(Request.model_validate(request()))
        self.assertIsInstance(result, GateDecision)
        self.assertEqual(result.decision, 'ALLOW')
        self.assertEqual(result.output.request_id, 'request-x')
        self.assertEqual(result.output.action_id, 'action-x')

    def test_cli_offline_and_invalid_json(self):
        completed = subprocess.run([sys.executable, '-m', 'gatekeeper', 'examples/read-file.json'],
                                   capture_output=True, text=True, check=True, timeout=10)
        result = json.loads(completed.stdout)
        self.assertEqual(result['mode'], 'offline-demo')
        self.assertEqual(result['output']['decision'], 'ASK')
        self.assertFalse(result['model_called'])
        bad = subprocess.run([sys.executable, '-m', 'gatekeeper', 'README.md'],
                             capture_output=True, text=True, timeout=10)
        self.assertEqual(bad.returncode, 2)

    def test_required_diagnostics_and_probabilities(self):
        for mode, make in [('single', response), ('decomposed', decomposed_response)]:
            for key in ('truncated', 'state_tokens_dropped', 'truncated_questions'):
                raw = make()
                del raw['usage'][key]
                result = parse_response(raw, mode)
                self.assertIsNone(result.decision)
                self.assertEqual(result.error_kind, 'invalid_response')
            for probabilities in (None, {}, {'ALLOW': True, 'ASK': 0, 'BLOCK': 0}):
                raw = make()
                next(iter(raw['answers'].values()))['probabilities'] = probabilities
                result = parse_response(raw, mode)
                self.assertIsNone(result.decision)
                self.assertEqual(result.error_kind, 'invalid_response')
            raw = make()
            raw['usage']['truncated'] = True
            result = parse_response(raw, mode)
            self.assertEqual(result.error_kind, 'truncation')
            self.assertIsNotNone(result.probabilities_by_question)
