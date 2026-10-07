import json
import argparse
from gatekeeper.laya_adapter import LayaBackend
from scripts.experiment import config, new_output_dir

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--question-mode', choices=('single', 'decomposed'), default='single')
    args = parser.parse_args()
    settings = config()
    output = new_output_dir(label='smoke-' + args.question_mode)
    backend = LayaBackend(settings['checkpoint'], settings['revision'], question_mode=args.question_mode)
    try:
        backend.initialize()
        text = json.dumps(backend.metadata, indent=2)
        (output / 'model_smoke.json').write_text(text, encoding='utf-8')
        print(text)
        return 2 if backend.error else 0
    finally:
        backend.close()

if __name__ == '__main__':
    raise SystemExit(main())
