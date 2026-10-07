"""Decision-only local demo. Model access requires --real-model."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
from . import Gatekeeper, LayaBackend
from .config import resolve_checkpoint
from .laya_adapter import Prediction


class DemoBackend:
    def predict(self, request):
        return Prediction(error='Offline demo: model not requested', error_kind='offline_demo')

    def close(self):
        pass


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('request', type=Path)
    parser.add_argument('--real-model', action='store_true')
    parser.add_argument('--checkpoint-profile', choices=('baseline', 'typed-decisions'), default='baseline')
    parser.add_argument('--revision')
    parser.add_argument('--question-mode', choices=('single', 'decomposed'), default='single')
    parser.add_argument('--cache-dir', type=Path)
    parser.add_argument('--load-timeout', type=float, default=300)
    parser.add_argument('--timeout', type=float, default=60)
    args = parser.parse_args(argv)
    try:
        request = json.loads(args.request.read_text(encoding='utf-8-sig'))
        checkpoint, revision = resolve_checkpoint(profile=args.checkpoint_profile, revision=args.revision)
        backend = LayaBackend(checkpoint, revision, timeout=args.timeout, load_timeout=args.load_timeout,
                              question_mode=args.question_mode, cache_dir=args.cache_dir) if args.real_model else DemoBackend()
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    with Gatekeeper(backend) as gate:
        result = gate.evaluate(request)
        value = asdict(result)
        value['output'] = result.output.model_dump()
        value['mode'] = 'real-model' if args.real_model else 'offline-demo'
        value['model'] = getattr(backend, 'metadata', None)
        print(json.dumps(value, indent=2, ensure_ascii=False))
        return 2 if args.real_model and result.error else 0


if __name__ == '__main__':
    raise SystemExit(main())
