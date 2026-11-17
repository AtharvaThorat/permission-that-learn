"""ASK check with the real laya-cybersec: the team's verified ASK cases, then the demo's ASK scenarios through the
whole plugin and permission memory (ask -> approve and remember -> same request answered by the grant -> revoke -> asked
again). A simulated person answers. Nothing real is touched; the scenarios run in the simulated Workspace.

    python -m grids_plugin.ask_check --laya-cache D:\\grids-plugin\\hf-cache
"""
import argparse
import json
import tempfile
import time
from pathlib import Path

def fmt(probabilities):
    return ' · '.join(f'{k} {v:.2f}' for k, v in probabilities.items()) if probabilities else '-'


def verified_cases(scanner, cases):
    """Each case's exact model state and question through the plugin's scanner (rotated method, no reduction)."""
    out = []
    for case in cases.values():
        result = scanner.decide(case['model_state'], profile='recorded_full')
        out.append({'id': case['id'], 'category': case['category'],
                    'saved': case['raw_output']['answers']['decision']['probabilities'],
                    'decision': result['decision'], 'probabilities': result['probabilities'], 'error': result['error'],
                    'seconds': result.get('seconds')})
    return out


def attempt(name, scanner, memory, answer, remember=False, wait=60.0):
    """One run of an ASK scenario's fixed action; the simulated person answers if asked."""
    from .session import VERIFIED_CASES, DemoSession, ask_case, verified_case
    case = verified_case(name) if name in VERIFIED_CASES else ask_case(name)
    session = DemoSession('wall_laya', 'Free chat', scanner, memory=memory, memory_mode='grants', row=case)
    thread, asked, deadline = session.start(case['prompt'], recorded=True), False, time.monotonic() + wait
    while thread.is_alive() and time.monotonic() < deadline:
        if session.pending:
            session.respond(answer, remember=remember and answer)
            asked = True
        time.sleep(0.05)
    thread.join(wait)
    row = next(iter(session.rows.values()), {})
    scan = session.gate.scans[0] if session.gate.scans else {}
    return {'wall': row.get('wall'), 'laya': row.get('gate_output'), 'raw': scan.get('decision'), 'asked': asked,
            'memory': row.get('memory'), 'executed': bool(row.get('executed')), 'error': session.error}


def scenario_loop(name, scanner, memory):
    """ask -> approve and remember; repeat -> grant; revoke; repeat -> asked again (rejected)."""
    first = attempt(name, scanner, memory, True, remember=True)
    second = attempt(name, scanner, memory, True)
    for grant in memory.grants():
        if grant['active']:
            memory.revoke(grant['id'])
    third = attempt(name, scanner, memory, False)
    return {'scenario': name, 'first': first, 'repeat': second, 'after_revoke': third,
            'passed': (first['asked'] and first['executed'] and first['memory'] == 'approved and remembered'
                       and not second['asked'] and second['executed'] and second['memory'] == 'answered by remembered permission'
                       and third['asked'] and not third['executed'])}


def checked_loop(name, scanner, memory):
    """`scenario_loop`, with an unexpected error recorded as a failed scenario instead of ending the whole check."""
    try:
        return scenario_loop(name, scanner, memory)
    except Exception as exc:
        empty = {'wall': None, 'laya': None, 'raw': None, 'asked': False, 'memory': None, 'executed': False,
                 'error': f'{type(exc).__name__}: {exc}'}
        return {'scenario': name, 'first': empty, 'repeat': empty, 'after_revoke': empty, 'passed': False,
                'error': empty['error']}


def report(cases, loops):
    asked = sum(c['decision'] == 'ASK' for c in cases)
    lines = ['# ASK check (real laya-cybersec)', '', "## Verified ASK cases (exact model state and question)", '',
             f'{asked} of {len(cases)} cases answered ASK.', '',
             '| Case | Category | Saved run | Plugin (rotated) | Decision |', '|---|---|---|---|---|']
    lines += [f"| {c['id']} | {c['category']} | {fmt(c['saved'])} | {fmt(c['probabilities'])} | **{c['decision'] or c['error']}** |"
              for c in cases]
    lines += ['', "## The page's ASK cases, with permission memory (verified cases: their model state and scope, "
              'no tool runs)', '',
              '| Scenario | laya-cybersec | 1. asked, approved and remembered | 2. same request | 3. after revoke | Passed |',
              '|---|---|---|---|---|---|']
    for loop in loops:
        f, r, a = loop['first'], loop['repeat'], loop['after_revoke']
        if loop.get('error'):
            lines.append(f"| {loop['scenario']} | error: {loop['error']} | | | | **no** |")
            continue
        lines.append(f"| {loop['scenario']} | {f['raw'] or '-'} ({f['laya'] or f['wall']}) | "
                     f"{'asked' if f['asked'] else 'not asked'}, {'ran' if f['executed'] else 'did not run'} | "
                     f"{r['memory'] or ('asked' if r['asked'] else r['raw'])}, {'ran' if r['executed'] else 'did not run'} | "
                     f"{'asked' if a['asked'] else 'not asked'}, {'ran' if a['executed'] else 'rejected'} | "
                     f"{'yes' if loop['passed'] else '**no**'} |")
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--laya-cache', required=True)
    parser.add_argument('--laya-device', default='cpu', choices=['cpu', 'cuda'])
    parser.add_argument('--cases', action='append', help="a verified ASK case file (repeatable); default: both of the "
                                                         "team's files in ask_cases/")
    parser.add_argument('--output', help='folder for report.md and summary.json (optional)')
    parser.add_argument('--record', action='store_true', help="also write each case's decision to "
                                                               'ask_cases/plugin_method_results.json (marks borderline cases on the page)')
    args = parser.parse_args(argv)
    from .cybersec import MODEL_ID, REVISION, Scanner, download
    from .memory import Memory
    from .session import ASK_SCENARIOS, PLUGIN_RESULTS_FILE, VERIFIED_CASES, VERIFIED_FILES
    from .session import verified_cases as load_cases
    scanner = Scanner(download(args.laya_cache), device=args.laya_device)
    cases = verified_cases(scanner, load_cases(args.cases or VERIFIED_FILES))
    if args.record:
        PLUGIN_RESULTS_FILE.write_text(json.dumps({
            'method': 'rotated: the decision question in three option orders in one call, probabilities averaged',
            'checkpoint': MODEL_ID, 'revision': REVISION, 'device': args.laya_device,
            'created': time.strftime('%Y-%m-%d'),
            'cases': {c['id']: {'decision': c['decision'], 'probabilities': c['probabilities'], 'error': c['error']}
                      for c in cases}}, indent=1) + '\n', encoding='utf-8')
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        memory = Memory(Path(folder) / 'permissions.sqlite', 'ask-check-user')
        loops = [checked_loop(name, scanner, memory) for name in list(VERIFIED_CASES) + list(ASK_SCENARIOS)]
    text = report(cases, loops)
    print(text)
    if args.output:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / 'report.md').write_text(text, encoding='utf-8')
        (out / 'summary.json').write_text(json.dumps({'cases': cases, 'scenarios': loops}, indent=1) + '\n', encoding='utf-8')
    return 0 if all(c['decision'] == 'ASK' for c in cases) and all(l['passed'] for l in loops) else 1


if __name__ == '__main__':
    raise SystemExit(main())
