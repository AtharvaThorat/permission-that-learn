"""Explicit checkpoint, one persistent CPU worker, no routing or tool execution."""
import importlib.util
import json
import math
import multiprocessing as mp
import os
import warnings
import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from .schemas import Request
from .questions import QUESTIONS, questions_for_mode, combine_answers, TEMPLATE_VERSIONS
from .state import model_state
from .config import resolve_checkpoint
from threading import RLock
from functools import wraps

CHECKPOINT = 'convaiinnovations/laya'


@dataclass
class Prediction:
    decision: str | None = None
    raw_decision: str | None = None
    raw: dict | None = None
    probabilities: dict | None = None
    called: bool = False
    error: str | None = None
    error_kind: str | None = None
    elapsed_seconds: float | None = None
    raw_answers: dict | None = None
    probabilities_by_question: dict | None = None
    ask_reason_code: str | None = None
    truncated: bool | None = None
    model_call_count: int | None = 0
    model_call_submissions: int = 0

def _parse_single_response(raw) -> Prediction:
    result = Prediction(raw=raw if isinstance(raw, dict) else None, called=True)
    try:
        answer = raw['answers']['decision']
        result.raw_decision = answer.get('choice')
        result.probabilities = answer.get('probabilities')
        if answer.get('type') != 'choice' or result.raw_decision not in ('ALLOW', 'ASK', 'BLOCK'):
            raise ValueError('Missing or invalid typed decision')
        usage = raw['usage']
        if usage.get('truncated') is not False or usage.get('state_tokens_dropped') != 0:
            raise ValueError('Truncated input or missing truncation diagnostics')
        if usage.get('truncated_questions') or usage.get('options'):
            raise ValueError('Question or option truncation/collapse')
        if answer.get('low_confidence') or raw.get('low_confidence'):
            raise ValueError('Provider abstained')
        probs = result.probabilities
        if (not isinstance(probs, dict) or set(probs) != {'ALLOW', 'ASK', 'BLOCK'} or
            any(type(v) not in (float, int) or not math.isfinite(v) or not 0 <= v <= 1 for v in probs.values()) or
            abs(sum(probs.values()) - 1) > 0.002):
            raise ValueError('Invalid class probabilities')
        # Provider confidence/answer_confidence remain raw; neither is substituted for P(choice).
        result.decision = result.raw_decision
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        result.error = f'{type(exc).__name__}: {exc}'
    return result

def parse_response(raw, question_mode='single') -> Prediction:
    questions = questions_for_mode(question_mode)
    if question_mode == 'single':
        # Same valid-response mapping; malformed distributions/diagnostics fail closed.
        result = _parse_single_response(raw)
    else:
        result = Prediction(raw=raw if isinstance(raw, dict) else None, called=True)
    result.model_call_count = 1
    result.model_call_submissions = 1
    answers = raw.get('answers') if isinstance(raw, dict) else None
    if isinstance(answers, dict):
        result.raw_answers = {qid: answers[qid].get('choice') for qid in questions
                              if isinstance(answers.get(qid), dict)}
        result.probabilities_by_question = {qid: answers[qid].get('probabilities') for qid in questions
                                           if isinstance(answers.get(qid), dict)}
    usage = raw.get('usage') if isinstance(raw, dict) else None
    if isinstance(usage, dict) and type(usage.get('truncated')) is bool:
        result.truncated = usage['truncated']
    if question_mode == 'single':
        return validate_diagnostics(result, raw, questions)
    try:
        if not isinstance(usage, dict) or usage.get('truncated') is not False or usage.get('state_tokens_dropped') != 0:
            raise ValueError('Truncated input or missing truncation diagnostics')
        if usage.get('truncated_questions') or usage.get('options'):
            raise ValueError('Question or option truncation/collapse')
        if not isinstance(answers, dict) or set(answers) != set(questions):
            raise ValueError('Missing or unexpected question answers')
        for qid, question in questions.items():
            answer = answers[qid]
            labels = set(question['criteria'])
            if not isinstance(answer, dict) or answer.get('type') != 'choice' or answer.get('choice') not in labels:
                raise ValueError(f'Invalid typed answer: {qid}')
            if answer.get('low_confidence') or raw.get('low_confidence'):
                raise ValueError('Provider abstained')
            probs = answer.get('probabilities')
            if (not isinstance(probs, dict) or set(probs) != labels or
                any(type(v) not in (float, int) or not math.isfinite(v) or not 0 <= v <= 1 for v in probs.values()) or
                abs(sum(probs.values()) - 1) > 0.002):
                raise ValueError(f'Invalid class probabilities: {qid}')
        result.decision, result.ask_reason_code = combine_answers(
            answers['task_relation']['choice'], answers['authorization_details']['choice'])
        # raw_decision remains None: the combined label is computed by code.
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        result.error = f'{type(exc).__name__}: {exc}'
    return validate_diagnostics(result, raw, questions)

def validate_diagnostics(result, raw, questions):
    usage = raw.get('usage') if isinstance(raw, dict) else None
    answers = raw.get('answers') if isinstance(raw, dict) else None
    if (not isinstance(usage, dict) or type(usage.get('truncated')) is not bool
        or type(usage.get('state_tokens_dropped')) is not int
        or not isinstance(usage.get('truncated_questions'), list)
        or not isinstance(answers, dict) or set(answers) != set(questions)):
        result.error = 'Missing or invalid required response diagnostics/answers'
    if result.error:
        result.decision = None
        truncated = isinstance(usage, dict) and (usage.get('truncated') is True
            or (type(usage.get('state_tokens_dropped')) is int and usage['state_tokens_dropped'] > 0)
            or bool(usage.get('truncated_questions')) or bool(usage.get('options')))
        result.error_kind = 'truncation' if truncated else 'invalid_response'
    return result


def synchronized(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapped


def _worker(pipe, checkpoint, revision, cache, question_mode):
    os.environ['HF_HOME'] = cache
    os.environ['HF_HUB_CACHE'] = str(Path(cache) / 'hub')
    os.environ['LAYA_CPU_AMP'] = '0'
    os.environ['USE_TF'] = '0'
    load_warnings = []
    def record_warnings(caught):
        for warning in caught:
            load_warnings.append({'message': str(warning.message), 'category': warning.category.__name__,
                                  'filename': warning.filename, 'lineno': warning.lineno})
            warnings.warn_explicit(warning.message, warning.category, warning.filename, warning.lineno)
    try:
        from laya import Agent
        load_started = perf_counter()
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter('always')
                agent = Agent(model_id_or_path=checkpoint, revision=revision, device='cpu',
                              fast=False, compile=False, backend='eager')
        finally:
            record_warnings(caught)
        torch = sys.modules.get('torch')
        pipe.send({'ready': True, 'actual_checkpoint': agent.model_id,
                   'revision': agent.revision, 'device': str(agent.device),
                   'config': agent.cfg, 'load_warnings': load_warnings,
                   'checkpoint_download_and_load_seconds': perf_counter() - load_started,
                   'runtime': {'dtype': str(getattr(agent, 'dtype', 'unknown')),
                               'cpu_threads': torch.get_num_threads() if torch else None,
                               'cpu_interop_threads': torch.get_num_interop_threads() if torch else None}})
        while True:
            state = pipe.recv()
            if state is None:
                break
            try:
                pipe.send({'raw': agent.system_one(state, questions_for_mode(question_mode)), 'api_calls': 1})
            except Exception as exc:
                pipe.send({'error': f'{type(exc).__name__}: {exc}', 'api_calls': 1})
    except Exception as exc:
        pipe.send({'error': f'{type(exc).__name__}: {exc}', 'load_warnings': load_warnings})
    finally:
        pipe.close()

class LayaBackend:
    def __init__(self, checkpoint=None, revision=None, timeout=60, load_timeout=300, question_mode='single', cache_dir=None):
        checkpoint, revision = resolve_checkpoint(checkpoint, revision)
        if any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in (timeout, load_timeout)):
            raise ValueError('Timeouts must be finite and positive')
        self._lock = RLock()
        self.closed = False
        self.error_kind = None
        self.cache_dir = str(Path(cache_dir or os.environ.get('LAYA_CACHE_DIR', '.cache/huggingface')).expanduser().resolve())
        questions_for_mode(question_mode)
        self.question_mode = question_mode
        self.checkpoint, self.revision = checkpoint, revision
        self.timeout, self.load_timeout = timeout, load_timeout
        self.process = self.pipe = None
        self.error = None
        self.initialized = False
        self.metadata = {'selected_checkpoint': checkpoint, 'requested_revision': revision,
                         'question_mode': question_mode, 'question_template_version': TEMPLATE_VERSIONS[question_mode], 'cache_dir': self.cache_dir, 'load_timeout_seconds': load_timeout, 'questions_per_call': len(questions_for_mode(question_mode)),
                         'actual_checkpoint': None, 'revision': None, 'device': None,
                         'requested_device': 'cpu', 'initialization_seconds': None,
                         'first_inference_seconds': None, 'smoke': None,
                         'thresholds': 'none; uncalibrated development argmax',
                         'load_warnings': [], 'checkpoint_download_and_load_seconds': None,
                         'inference_settings': {'device': 'cpu', 'backend': 'eager', 'fast': False,
                            'compile': False, 'LAYA_CPU_AMP': '0', 'USE_TF': '0',
                            'warmup': 'one identical notes-7 smoke request before fixtures',
                            'max_len_override': None, 'head_max_len_override': None,
                            'min_confidence': None},
                         'inference_timeout_seconds': timeout}

    @synchronized
    def initialize(self):
        """Load once and warm up with the unchanged notes-7 request; inspect error/metadata."""
        if self.closed:
            if not self.error:
                self.error, self.error_kind = "Backend is closed", "closed"
            return
        if self.initialized:
            return
        self.initialized = True
        started = perf_counter()
        try:
            if importlib.util.find_spec('laya') is None:
                raise ModuleNotFoundError("No module named 'laya'; dependency installation is required")
            context = mp.get_context('spawn')
            self.pipe, child = context.Pipe()
            self.process = context.Process(target=_worker, args=(child, self.checkpoint, self.revision,
                                               self.cache_dir, self.question_mode), daemon=True)
            try:
                self.process.start()
            finally:
                child.close()
            if not self.pipe.poll(self.load_timeout):
                raise TimeoutError('Checkpoint initialization timed out')
            status = self.pipe.recv()
            if not status.get('ready'):
                self.metadata['load_warnings'] = status.get('load_warnings', [])
                raise RuntimeError(status.get('error', 'Worker did not initialize'))
            self.metadata.update({k: v for k, v in status.items() if k != 'ready'})
            if status.get('device') != 'cpu':
                raise RuntimeError('Loaded device does not match requested CPU')
            if self.revision and status.get('revision') != self.revision:
                raise RuntimeError('Loaded revision does not match the explicitly requested revision')
            if status.get('actual_checkpoint') != self.checkpoint:
                raise RuntimeError('Loaded checkpoint does not match the explicitly requested checkpoint')
        except Exception as exc:
            self.error = f'{type(exc).__name__}: {exc}'
            self.error_kind = 'initialization_timeout' if isinstance(exc, TimeoutError) else 'download_or_load_failure'
            self.close()
        self.metadata['initialization_seconds'] = perf_counter() - started
        self.metadata['initialization_error'] = self.error
        if self.error is None:
            started = perf_counter()
            smoke = self._infer(json.dumps({'authentic_user_request': 'Read file notes-7.',
                          'untrusted_proposed_action': {'tool': 'files.read', 'arguments': {'file_id': 'notes-7'}},
                          'verified_context': {'confirmation_required': False, 'evidence_complete': True,
                                               'facts': {'accessible_file_ids': ['notes-7']}}}))
            self.metadata['first_inference_seconds'] = perf_counter() - started
            self.metadata['smoke'] = vars(smoke)
            if smoke.error:
                self.error = 'Minimal inference failed: ' + smoke.error
                self.error_kind = smoke.error_kind
                self.close()

        self.metadata['initialization_error_kind'] = self.error_kind
        self.metadata['warmup_error'] = (self.metadata.get('smoke') or {}).get('error')

    def _infer(self, state):
        called = False
        started = perf_counter()
        def timed(result):
            result.elapsed_seconds = perf_counter() - started
            return result
        try:
            if not self.process or not self.process.is_alive():
                raise RuntimeError('Model worker unavailable')
            self.pipe.send(state)
            called = True  # Submitted to the loaded worker; errors need not complete a forward pass.
            if not self.pipe.poll(self.timeout):
                raise TimeoutError('Inference timed out')
            response = self.pipe.recv()
            if 'error' in response:
                return timed(Prediction(called=True, error=response['error'], error_kind='inference_failure',
                                       model_call_count=response['api_calls'], model_call_submissions=1))
            return timed(parse_response(response['raw'], self.question_mode))
        except Exception as exc:
            self.error = f'{type(exc).__name__}: {exc}'
            self.error_kind = 'inference_timeout' if isinstance(exc, TimeoutError) else 'inference_failure'
            self.close()
            return timed(Prediction(called=called, error=self.error, error_kind=self.error_kind,
                                   model_call_count=None if called else 0, model_call_submissions=int(called)))

    @synchronized
    def predict(self, req):
        self.initialize()
        if self.error:
            return Prediction(error=self.error, error_kind=self.error_kind)
        return self._infer(model_state(req))

    @synchronized
    def close(self):
        """Idempotent shutdown; terminate a stuck worker after a bounded grace period."""
        self.closed = True
        if self.process:
            if self.process.is_alive() and not self.error:
                try:
                    self.pipe.send(None)
                    self.process.join(timeout=1)
                except (OSError, EOFError):
                    pass
            if self.process.is_alive():
                self.process.terminate()
            try:
                self.process.join(timeout=5)
            except AssertionError:
                pass  # Process.start failed before a child was created.
            self.process = None
        if self.pipe:
            self.pipe.close()
            self.pipe = None

    def __enter__(self):
        self.initialize()
        return self

    def __exit__(self, *exc):
        self.close()
