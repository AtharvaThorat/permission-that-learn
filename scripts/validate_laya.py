"""Explicit real CPU load plus short/long-input probes, separate from benchmark scores."""
import argparse
import importlib.metadata
import os
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--allow-models', action='store_true')
    parser.add_argument('--max-input-tokens', type=int, default=None)
    parser.add_argument('--input-profile', choices=['legacy_compact', 'full_evidence', 'evidence_v2'], default='evidence_v2')
    args = parser.parse_args()
    if not args.allow_models:
        parser.error('Real inference requires --allow-models')
    args.output.mkdir(parents=True, exist_ok=False)
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', USE_TF='0', LAYA_CPU_AMP='0')
    from experiment.artifacts import atomic
    from gatekeeper.laya_adapter import LayaBackend
    from gatekeeper.schemas import Request
    backend = LayaBackend(cache_dir=args.cache_dir, timeout=300, load_timeout=600,
                          max_input_tokens=args.max_input_tokens, context_profile=args.input_profile)
    evidence = {'kind': 'controlled_real_laya_not_benchmark', 'python': platform.python_version(),
                'packages': {name: importlib.metadata.version(name) for name in
                             ('laya', 'torch', 'transformers', 'tokenizers', 'huggingface-hub')},
                'probes': []}
    try:
        backend.initialize()
        if not backend.error:
            for label, text in [('short', 'Meeting notes.'),
                                ('medium', 'Untrusted tool output. ' * 160),
                                ('long', 'Untrusted tool output. ' * 1000),
                                ('overflow', 'Untrusted tool output. ' * 3000)]:
                request = Request.model_validate({'schema_version': '0.1', 'request_id': label,
                    'task_id': 'controlled', 'user_request': 'Read file notes-7 and summarize it.',
                    'action': {'action_id': label, 'tool': 'get_file_by_id', 'arguments': {'file_id': 'notes-7'}},
                    'wall': {'verdict': 'PASS', 'policy_version': 'controlled',
                             'evaluated_action_id': label, 'reason_codes': ['POLICY_PASS']},
                    'verified_context': {'confirmation_required': False, 'evidence_complete': True,
                        'facts': {'resource_id': 'notes-7', 'untrusted_tool_output': text}}})
                prediction = backend.predict(request)
                evidence['probes'].append({'label': label, 'request': request.model_dump(),
                                           'prediction': vars(prediction)})
                print(label, prediction.decision, prediction.error_kind, prediction.elapsed_seconds, flush=True)
                atomic(args.output / 'progress.json', evidence)
    finally:
        evidence['backend'] = backend.metadata
        evidence['error'] = backend.error
        atomic(args.output / 'laya.json', evidence)
        backend.close()
    print('Laya initialized:', backend.error is None, 'probes:', len(evidence['probes']))
    return 1 if evidence['error'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
