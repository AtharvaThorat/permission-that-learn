"""TextCortex/laya-cybersec as the Gatekeeper model, with the team's rotated-option ALLOW / ASK / BLOCK method.

laya-cybersec is fine-tuned from Laya (mmBERT-base encoder, 321.9M parameters). As in the team's permission study
(`grids.evaluation.permission_sim`, the team's method of 2026-11-10), it is asked the repository's decision
question three times in one model call, with the ALLOW, ASK and BLOCK options in rotated orders. Every answer and the
truncation diagnostics are validated; the probabilities are averaged by label and the highest wins (a tie is ASK).
Any failure is an error, never an ALLOW.
"""
import threading
import time
from pathlib import Path

MODEL_ID = 'TextCortex/laya-cybersec'
REVISION = '41fd5a2dfced0fb357974afd780a3ed6e7c43838'
PARAMETERS = 321_908_998                      # release_manifest.json
# PyTorch weights only; the card's 1.3 GB ONNX copy is not needed.
FILES = ['rl_agent_config.json', 'model.safetensors', 'tokenizer/*', 'encoder/*', 'release_manifest.json']
METHOD = 'single-v1-rotated'


def decision_question():
    """The repository's ALLOW / ASK / BLOCK question (single-v1), in the dataset question format."""
    from grids.gatekeeper.questions import QUESTIONS
    return {'decision': QUESTIONS['decision']}


def download(cache_dir):
    """Download the pinned revision into `<cache_dir>/hub` and return the snapshot folder."""
    from huggingface_hub import snapshot_download
    return snapshot_download(MODEL_ID, revision=REVISION, cache_dir=str(Path(cache_dir) / 'hub'), allow_patterns=FILES)


class Scanner:
    """The loaded model. `decide` is the one function used both live and for the dataset evaluation."""

    def __init__(self, snapshot, device='cpu', question=None):
        import laya
        from grids.evaluation.permission_sim import rotated_questions
        started = time.perf_counter()
        self.agent = laya.Agent(str(snapshot), device=device)
        self.load_seconds = time.perf_counter() - started
        self.device = device
        self.question = question or decision_question()
        self.asked = rotated_questions(self.question)
        self.lock = threading.Lock()

    def decide(self, state, profile='compact_v1'):
        """One model call on one JSON state. `profile`: `compact_v1` for live actions (the repository's reduction for
        this model's 1,024 tokens), `recorded_full` for dataset rows that are already compact."""
        from grids.evaluation.permission_sim import rotated_decision
        from grids.gatekeeper.context import ContextError, preflight
        record = {'decision': None, 'probabilities': None, 'answers': None, 'error': None, 'error_kind': None,
                  'tie': False, 'state_tokens': None, 'sequence_tokens': None}
        with self.lock:
            started = time.perf_counter()
            try:
                prepared, diagnostics = preflight(self.agent, state, self.asked, {}, profile=profile, max_chars=None)
                record.update(state_tokens=diagnostics.get('prepared_token_count'),
                              sequence_tokens=max(diagnostics.get('sequence_tokens') or [0]),
                              evidence_excerpts=diagnostics.get('evidence_excerpts'))
                raw = self.agent.system_one(prepared, self.asked)   # one call, all three option orders
                decision, mean, answers = rotated_decision(raw, self.asked)
                top = max(mean.values())
                record.update(decision=decision, probabilities=mean, answers=answers,
                              tie=sum(top - value <= 1e-9 for value in mean.values()) > 1)
            except ContextError as exc:
                record.update(error=str(exc), error_kind=exc.kind)
            except ValueError as exc:
                record.update(error=f'ValueError: {exc}', error_kind='invalid_response')
            except Exception as exc:
                record.update(error=f'{type(exc).__name__}: {exc}', error_kind='inference_failure')
            record['seconds'] = time.perf_counter() - started
        return record
