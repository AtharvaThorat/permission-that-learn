"""AST/JSON/diff checks only. No application imports or test execution."""
import ast
import json
import subprocess
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    files = [p for name in ('blackbox', 'integrations', 'tests/blackbox') for p in (root / name).rglob('*.py')]
    files += [root / 'gatekeeper/policy.py', root / 'scripts/colab_blackbox.py', Path(__file__).resolve()]
    trees = {p: ast.parse(p.read_text(encoding='utf-8-sig'), filename=str(p)) for p in files}
    configs = list((root / 'configs/blackbox').rglob('*.json'))
    for path in configs:
        json.loads(path.read_text(encoding='utf-8-sig'))
    dispatches = [(p.relative_to(root).as_posix(), n.lineno) for p, tree in trees.items()
                  if 'tests' not in p.relative_to(root).parts
                  for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                  and n.func.attr == 'run_function']
    if len(dispatches) != 1 or dispatches[0][0] != 'blackbox/execution.py':
        raise RuntimeError('Unexpected native dispatch location: ' + repr(dispatches))
    subprocess.run(['git', 'diff', '--check'], cwd=root, check=True)
    preserved = ['gatekeeper/questions.py', 'gatekeeper/state.py',
                 'gatekeeper/model_manifest.json', 'requirements.txt', 'requirements-lock.txt', 'requirements-test.txt']
    subprocess.run(['git', 'diff', '--exit-code', 'HEAD', '--', *preserved], cwd=root, check=True)
    print(json.dumps({'python_files_ast_parsed': len(files), 'json_files_parsed': len(configs),
                      'native_dispatch_locations': dispatches, 'retained_laya_core': 'unchanged relative to HEAD except gatekeeper/policy.py',
                      'application_imports': 'NOT RUN', 'tests': 'NOT RUN', 'runtime': 'NOT RUN'}, indent=2))


if __name__ == '__main__':
    main()
