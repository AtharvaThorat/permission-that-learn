"""Explicit CLI: offline validation by default, execution only by opt-in."""
import argparse
import json
from pathlib import Path
from .spec import load, plan
from .aggregate import aggregate


def main():
    parser = argparse.ArgumentParser(prog='python -m experiment')
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('validate','plan','run','estimate'):
        p = commands.add_parser(name)
        p.add_argument('--config', required=True)
        if name == 'run':
            p.add_argument('--output', default='results/experiments')
            p.add_argument('--allow-models', action='store_true')
            p.add_argument('--actors', nargs='+')
        if name == 'estimate':
            p.add_argument('--measurements')
    for name in ('resume','aggregate'):
        p = commands.add_parser(name)
        p.add_argument('--run-dir', required=True)
        if name == 'resume':
            p.add_argument('--allow-models', action='store_true')
            p.add_argument('--retry-status', action='append', default=[])
            p.add_argument('--actors', nargs='+')
        else:
            p.add_argument('--attempt-policy', choices=['earliest','latest'], default='earliest')
    p = commands.add_parser('compare')
    p.add_argument('--run-dirs', nargs='+', required=True)
    p = commands.add_parser('report')
    p.add_argument('--run-dir', required=True)
    p = commands.add_parser('replay')
    p.add_argument('--source-run', required=True)
    p.add_argument('--config', required=True)
    p.add_argument('--allow-models', action='store_true')
    args = parser.parse_args()
    if args.command in ('validate','plan','estimate'):
        resolved = plan(load(args.config))
        if args.command == 'estimate':
            from .estimate import estimate
            result = estimate(resolved, json.loads(Path(args.measurements).read_text()) if args.measurements else {})
        else:
            result = {k:v for k,v in resolved.items() if k not in ('jobs','identity')}
    elif args.command == 'aggregate':
        result = aggregate(args.run_dir, args.attempt_policy)
    elif args.command == 'report':
        from .report import report
        result = {'report': report(args.run_dir)}
    elif args.command == 'compare':
        # Preserve distinct run/configuration groups; no accidental pooling.
        result = {str(Path(p)):aggregate(p) for p in args.run_dirs}
    elif args.command == 'replay':
        from .replay import replay
        result = replay(args.source_run, json.loads(Path(args.config).read_text()), allow_models=args.allow_models)
    else:
        if not args.allow_models:
            parser.error('Execution requires --allow-models and user-provided existing endpoints/assets')
        from .store import create_run, compatible
        from .services import Services
        from .scheduler import schedule
        from .runtime import execute
        if args.command == 'run':
            spec = load(args.config)
            directory = create_run(spec, args.output)
        else:
            directory = Path(args.run_dir)
            spec = load(directory/'spec.json')
        resolved = compatible(directory, spec)
        services = Services(spec)
        try:
            schedule(spec, resolved, directory,
                     lambda *a: execute(spec, services, directory, *a),
                     actors=args.actors, retry_statuses=getattr(args,'retry_status', []))
        finally:
            services.close()
        result = {'run_dir':str(directory), 'summary':aggregate(directory)}
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
