"""One public command tree; heavy model packages load only for explicit commands."""
import argparse
import json
from pathlib import Path


def main(argv=None):
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog='grids', description='Authorization evaluation and native AgentDojo experiments')
    parser.add_argument('command', choices=['setup', 'models', 'serve', 'validate', 'benchmark', 'dataset', 'evaluate', 'report'])
    if not argv or argv[0] in ('-h', '--help'):
        parser.print_help()
        return
    args = parser.parse_args(argv[:1])
    rest = argv[1:]
    if args.command == 'setup':
        from .setup import main as setup
        return setup(['install', *rest])
    if args.command == 'serve':
        from grids.actors.serving import main as serve
        return serve(rest)
    if args.command == 'models':
        if rest and rest[0] == 'download':
            from .setup import main as setup
            return setup(['download', *rest[1:]])
        from grids.actors.profiles import load_profile
        from grids.paths import ROOT
        if rest not in ([], ['list']): parser.error('models list | models download --help')
        print(json.dumps({p.stem: load_profile(p) for p in sorted((ROOT/'configs/models').glob('*.json'))}, indent=2))
        return
    if args.command == 'validate':
        if rest and rest[0] == 'laya':
            from .validate_laya import main as validate
        elif rest and rest[0] == 'actor':
            from .validate_actor import main as validate
        else: parser.error('validate laya --help | validate actor --help')
        return validate(rest[1:])
    if args.command == 'benchmark':
        if rest and rest[0] == 'config':
            from .setup import main as setup
            return setup(rest)
        from .benchmark import main as benchmark
        return benchmark(rest)
    sub = argparse.ArgumentParser(prog='grids '+args.command)
    if args.command == 'dataset':
        sub.add_argument('operation', choices=['capture', 'validate', 'export-labels', 'import-labels'])
        sub.add_argument('--run-dir', action='append')
        sub.add_argument('--dataset')
        sub.add_argument('--labels')
        sub.add_argument('--output')
        a = sub.parse_args(rest)
        from grids.evaluation import dataset
        if a.operation == 'capture':
            if not a.run_dir or not a.output: sub.error('capture requires --run-dir and --output')
            result = dataset.capture(a.run_dir, a.output)
        else:
            if not a.dataset: sub.error('--dataset is required')
            if a.operation == 'validate': result = dataset.load_dataset(a.dataset)[0]
            else:
                if not a.output: sub.error('--output is required')
                if a.operation == 'export-labels': result = dataset.export_labels(a.dataset, a.output)
                else:
                    if not a.labels: sub.error('--labels is required')
                    result = dataset.import_labels(a.dataset, a.labels, a.output)
    elif args.command == 'evaluate':
        sub.add_argument('--dataset', required=True)
        sub.add_argument('--config', required=True)
        sub.add_argument('--output', required=True)
        sub.add_argument('--allow-models', action='store_true')
        a = sub.parse_args(rest)
        from grids.evaluation.replay import evaluate
        result = evaluate(a.dataset, json.loads(Path(a.config).read_text(encoding='utf-8')), a.output, allow_models=a.allow_models)
    else:
        sub.add_argument('--run-dir')
        sub.add_argument('--dataset')
        sub.add_argument('--evaluation')
        sub.add_argument('--labels')
        sub.add_argument('--output')
        a = sub.parse_args(rest)
        if a.run_dir:
            if a.dataset or a.evaluation or a.labels or a.output: sub.error('Select live run OR authorization report')
            from grids.runs.report import report
            from grids.runs.aggregate import aggregate
            result = {'summary': aggregate(a.run_dir), 'report': report(a.run_dir)}
        else:
            if not all((a.dataset, a.evaluation, a.output)): sub.error('--dataset, --evaluation and --output are required')
            from grids.evaluation.metrics import report
            result = report(a.dataset, a.evaluation, a.output, a.labels)
    print(json.dumps(result, indent=2))
