"""Reset an AgentDojo WorkspaceEnvironment to the pristine baseline for user_task_0.

Usage (within an episode before calling pipeline.query):

    from scripts.reset_workspace import reset

    task, env, runtime = environment()
    reset(env)                     # restore to clean state in-place
    pipeline.query(task.PROMPT, runtime, env)

Or to obtain a fresh pristine copy without mutating an existing object:

    from scripts.reset_workspace import pristine_env
    env = pristine_env()

Only the workspace suite (v1.2.2) and user_task_0 are supported here.
Do not call this inside a running episode; call it between episodes.
"""
from pathlib import Path
import sys

# Allow running directly from the repository root.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_WALL_SRC = _REPO_ROOT / 'wall' / 'src'
for _p in (_REPO_ROOT, _WALL_SRC):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)

from integrations.agentdojo.task_selector import environment, SUITE_VERSION, SUITE_NAME, TASK_ID


def _load_pristine(verify_revision=True):
    """Return a freshly loaded pristine (task, env) pair."""
    task, env, runtime = environment(verify_revision=verify_revision)
    return task, env, runtime


def pristine_env(verify_revision=True):
    """Return a fresh pristine WorkspaceEnvironment with user_task_0 applied.

    This is the canonical baseline.  Call once per episode, not shared.
    """
    _, env, _ = _load_pristine(verify_revision=verify_revision)
    return env


def reset(env, verify_revision=True):
    """Reset an existing WorkspaceEnvironment to the pristine baseline in-place.

    Replaces inbox, calendar, and cloud_drive contents with the clean defaults
    for user_task_0.  No injection vectors are applied.

    Parameters
    ----------
    env:
        A WorkspaceEnvironment instance to reset.
    verify_revision:
        Forward to environment(); set False only in CPU unit tests.
    """
    _, fresh, _ = _load_pristine(verify_revision=verify_revision)
    # Replace mutable fields with their pristine counterparts using the
    # model_dump / model_validate round-trip so every field is covered.
    import json
    from agentdojo.default_suites.v1.workspace.task_suite import WorkspaceEnvironment
    snapshot = fresh.model_dump(mode='json')
    restored = WorkspaceEnvironment.model_validate(snapshot)
    env.inbox = restored.inbox
    env.calendar = restored.calendar
    env.cloud_drive = restored.cloud_drive


def _report(env):
    """Print a brief human-readable state summary for a workspace environment."""
    cal = env.calendar
    inbox = env.inbox
    drive = env.cloud_drive
    print(f'  calendar.current_day : {cal.current_day}')
    print(f'  calendar events      : {len(cal.events)}')
    print(f'  inbox emails         : {len(inbox.emails)}')
    print(f'  cloud_drive files    : {len(drive.files)}')


def _verify_digest(env, label='env'):
    """Return a stable fingerprint of the environment state for verification."""
    from blackbox.actions import digest
    return digest(env.model_dump(mode='json'))


def main():
    """CLI: verify the reset produces a reproducible pristine state."""
    print(f'Suite  : {SUITE_VERSION} / {SUITE_NAME}')
    print(f'Task   : {TASK_ID}')
    print()

    print('Loading pristine baseline ...')
    task, env_a, runtime = _load_pristine(verify_revision=False)
    digest_a = _verify_digest(env_a, 'pristine-a')
    print(f'Baseline state ({TASK_ID}):')
    _report(env_a)
    print(f'  digest: {digest_a}')
    print()

    print('Loading second pristine copy ...')
    _, env_b, _ = _load_pristine(verify_revision=False)
    digest_b = _verify_digest(env_b, 'pristine-b')
    print(f'Second copy digest: {digest_b}')
    if digest_a != digest_b:
        raise RuntimeError('Pristine copies produce different digests — non-deterministic environment.')
    print('Determinism check: PASS (two pristine loads produce identical digests)')
    print()

    print('Simulating a mutation on env_a ...')
    # Simulate a mutation (e.g. agent called get_unread_emails which marks emails read)
    for email in env_a.inbox.emails.values():
        email.read = True
    digest_mutated = _verify_digest(env_a, 'mutated')
    print(f'Mutated digest: {digest_mutated}')
    if digest_mutated == digest_a:
        print('  (mutation did not change digest — no read-state in this snapshot)')
    else:
        print('  Mutation detected in digest.')
    print()

    print('Resetting env_a to pristine baseline ...')
    reset(env_a, verify_revision=False)
    digest_reset = _verify_digest(env_a, 'after-reset')
    print(f'Reset digest : {digest_reset}')
    if digest_reset != digest_a:
        raise RuntimeError(f'Reset digest {digest_reset!r} != pristine {digest_a!r}')
    print('Reset verification: PASS')
    print()
    print(f'Task prompt  : {task.PROMPT}')
    print(f'Ground truth : {task.GROUND_TRUTH_OUTPUT}')


if __name__ == '__main__':
    main()
