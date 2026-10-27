"""Explicit CLI: offline validation by default, execution only by opt-in."""
import argparse
import json
from pathlib import Path
from .spec import load, plan
from .aggregate import aggregate


def main():
    parser = argparse.ArgumentParser(prog='python -m experiment')
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('discover')
    p.add_argument('--suite', choices=['workspace', 'slack', 'banking'], action='append')
    for name in ('validate','plan','run','estimate'):
        p = commands.add_parser(name)
        p.add_argument('--config', required=True)
        if name == 'run':
            p.add_argument('--output', default='results/experiments')
            p.add_argument('--allow-models', action='store_true')
            p.add_argument('--actors', nargs='+')
            p.add_argument('--approval-dir')
            p.add_argument('--approval-wait-seconds', type=float, default=0)
        if name == 'estimate':
            p.add_argument('--measurements')
    for name in ('resume','aggregate'):
        p = commands.add_parser(name)
        p.add_argument('--run-dir', required=True)
        if name == 'resume':
            p.add_argument('--allow-models', action='store_true')
            p.add_argument('--retry-status', action='append', default=[])
            p.add_argument('--actors', nargs='+')
            p.add_argument('--approval-dir')
            p.add_argument('--approval-wait-seconds', type=float, default=0)
        else:
            p.add_argument('--attempt-policy', choices=['earliest','latest'], default='earliest')
    p = commands.add_parser('compare')
    p.add_argument('--run-dirs', nargs='+', required=True)
    p = commands.add_parser('report')
    p.add_argument('--run-dir', required=True)
    p = commands.add_parser('approval')
    p.add_argument('--pending', required=True)
    p.add_argument('--decision', choices=['approve', 'reject'], required=True)
    p = commands.add_parser('replay')
    p.add_argument('--source-run', required=True)
    p.add_argument('--config', required=True)
    p.add_argument('--allow-models', action='store_true')
    args = parser.parse_args()
    if args.command == 'discover':
        from integrations.agentdojo.discovery import discover, SUITES
        result = {suite: discover(suite) for suite in (args.suite or SUITES)}
    elif args.command in ('validate','plan','estimate'):
        resolved = plan(load(args.config))
        if args.command == 'estimate':
            from .estimate import estimate
            result = estimate(resolved, json.loads(Path(args.measurements).read_text()) if args.measurements else {})
        else:
            result = {k:v for k,v in resolved.items() if k not in ('jobs','identity')}
    elif args.command == 'approval':
        from blackbox.permissions.approvals import respond
        result = {'response': respond(args.pending, args.decision == 'approve'),
                  'note': 'Feedback only; execution requires the original live episode and valid binding.'}
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
        if not 0 <= args.approval_wait_seconds <= 3600:
            parser.error('Approval wait must be between 0 and 3600 seconds')
        if args.approval_wait_seconds and not args.approval_dir:
            parser.error('--approval-wait-seconds requires --approval-dir')
        services = Services(spec, approval_directory=args.approval_dir,
                            approval_wait_seconds=args.approval_wait_seconds)
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
