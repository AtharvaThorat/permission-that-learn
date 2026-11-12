"""Trusted local permission administration and controlled validation."""
import argparse
from dataclasses import fields
import json
from pathlib import Path

from grids.core.contracts import BoundAction
from grids.core.permissions.store import PermissionStore, scope_for


def main(argv=None):
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ('simulate', 'laya-predict'):
        from grids.evaluation.permission_sim import main as legacy
        return legacy(argv)
    parser = argparse.ArgumentParser(prog='grids permissions')
    commands = parser.add_subparsers(dest='operation', required=True)
    for name in ('grant', 'list', 'revoke', 'review', 'export'):
        sub = commands.add_parser(name)
        sub.add_argument('--store', required=True)
        sub.add_argument('--user', required=True, help='Trusted local operator identity; never actor-provided')
        if name == 'grant':
            sub.add_argument('--pending', required=True, help='Exact pending JSON written by the operator channel')
            sub.add_argument('--ttl-seconds', type=float, default=86400)
            sub.add_argument('--max-uses', type=int)
        if name == 'revoke':
            sub.add_argument('--grant-id', required=True)
        if name == 'review':
            sub.add_argument('--file', required=True, help='Reviewed feedback JSON; see permission guide')
        if name == 'export':
            sub.add_argument('--output', required=True)
    sub = commands.add_parser('check')
    sub.add_argument('--output', required=True)
    sub.add_argument('--real-laya', action='store_true')
    sub.add_argument('--cache')
    sub = commands.add_parser('report')
    sub.add_argument('--run-dir', required=True)
    args = parser.parse_args(argv)
    if args.operation == 'check':
        from grids.evaluation.permission_checks import run
        result = run(args.output, real_laya=args.real_laya, cache=args.cache)
    elif args.operation == 'report':
        from grids.evaluation.permission_checks import report
        result = report(Path(args.run_dir))
    else:
        store = PermissionStore(args.store)
        if args.operation == 'grant':
            pending = json.loads(Path(args.pending).read_text(encoding='utf-8'))
            action = BoundAction(**{f.name: pending['action'][f.name] for f in fields(BoundAction)})
            if not pending.get('request') or not action.evidence_complete:
                parser.error('A complete pending record with the authentic request is required')
            result = {'grant_id': store.issue(args.user, scope_for(pending['request'], action),
                                              args.ttl_seconds, args.max_uses)}
        elif args.operation == 'list':
            result = store.list(args.user)
        elif args.operation == 'revoke':
            result = {'revoked': store.revoke(args.user, args.grant_id)}
        elif args.operation == 'review':
            result = {'applied': store.review(args.user, **json.loads(Path(args.file).read_text(encoding='utf-8')))}
        else:
            rows = store.export(args.user)
            with Path(args.output).open('x', encoding='utf-8') as stream:
                for row in rows:
                    stream.write(json.dumps(row, ensure_ascii=False) + '\n')
            result = {'exported': len(rows), 'output': args.output}
    print(json.dumps(result, indent=2))
