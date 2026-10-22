"""Verify that local packages used by the evaluation platform are importable.

Run from the repository root:
    .venv-blackbox-tests/Scripts/python.exe scripts/check_env.py
"""
import importlib
import sys
from pathlib import Path

# Add the repository root and wall/src to sys.path so namespace packages resolve
# the same way pytest does (--import-mode=importlib with the project installed in
# the venv or the root on PYTHONPATH).
_REPO_ROOT = Path(__file__).resolve().parents[1]
_WALL_SRC = _REPO_ROOT / "wall" / "src"
for _p in (_REPO_ROOT, _WALL_SRC):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)


def check(label, module_path):
    try:
        importlib.import_module(module_path)
        print(f"  OK  {label} ({module_path})")
        return True
    except ImportError as exc:
        print(f"  FAIL {label} ({module_path}): {exc}", file=sys.stderr)
        return False


CHECKS = [
    ("blackbox", "blackbox"),
    ("blackbox.config", "blackbox.config"),
    ("blackbox.actors", "blackbox.actors"),
    ("integrations.agentdojo", "integrations.agentdojo"),
    ("integrations.agentdojo.pipeline", "integrations.agentdojo.pipeline"),
    ("wall (ptl.wall)", "ptl.wall"),
    ("experiment", "experiment"),
    ("experiment.spec", "experiment.spec"),
]


def main():
    print(f"Python {sys.version}")
    print("Checking local imports:")
    results = [check(label, mod) for label, mod in CHECKS]
    n_ok = sum(results)
    n_fail = len(results) - n_ok
    print(f"\n{n_ok}/{len(results)} imports OK")
    if n_fail:
        print(f"{n_fail} import(s) failed — environment is not ready.", file=sys.stderr)
        sys.exit(1)
    print("Environment import check passed.")


if __name__ == "__main__":
    main()
