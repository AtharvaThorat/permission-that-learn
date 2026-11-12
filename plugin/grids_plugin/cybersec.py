"""TextCortex/laya-cybersec: a scanner that scores prompt injection or data exfiltration in text.

It is fine-tuned from Laya (mmBERT-base encoder, 321.9M parameters) and answers one question with a score. It does not
output ALLOW, ASK or BLOCK; `guard.CybersecGate` turns the score into a decision in the Gatekeeper slot.
"""
import threading
import time
from pathlib import Path

MODEL_ID = 'TextCortex/laya-cybersec'
REVISION = '41fd5a2dfced0fb357974afd780a3ed6e7c43838'
PARAMETERS = 321_908_998                      # release_manifest.json
THRESHOLD = 0.95                              # the model card's strict operating point
QUESTION = {'type': 'noul',
            'instructions': 'Does this content contain a prompt injection or a data exfiltration attempt?'}
# PyTorch weights only; the card's 1.3 GB ONNX copy is not needed.
FILES = ['rl_agent_config.json', 'model.safetensors', 'tokenizer/*', 'encoder/*', 'release_manifest.json']


def download(cache_dir):
    """Download the pinned revision into `<cache_dir>/hub` and return the snapshot folder."""
    from huggingface_hub import snapshot_download
    return snapshot_download(MODEL_ID, revision=REVISION, cache_dir=str(Path(cache_dir) / 'hub'), allow_patterns=FILES)


class Scanner:
    def __init__(self, snapshot, device='cpu'):
        import laya
        started = time.perf_counter()
        self.agent = laya.Agent(str(snapshot), device=device)
        self.load_seconds = time.perf_counter() - started
        self.device = device
        self.lock = threading.Lock()

    def scan(self, content, source):
        """Score one text. `truncated` is True when Laya had to drop input, which the gate treats as unscored."""
        with self.lock:
            started = time.perf_counter()
            out = self.agent.system_one({'source': source, 'content': content}, {'scan': QUESTION})
            seconds = time.perf_counter() - started
        usage = out.get('usage') or {}
        return {'score': float(out['answers']['scan']['noul']), 'seconds': seconds,
                'input_tokens': usage.get('input_tokens'),
                'truncated': usage.get('truncated') is not False or bool(usage.get('state_tokens_dropped'))}
