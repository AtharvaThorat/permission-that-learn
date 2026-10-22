"""Pristine environment factory and tool schemas for workspace/user_task_0.

Exports two public callables used by experiment runners:

  environment()  ->  (task, env, runtime)
      Returns a freshly loaded, unmodified WorkspaceEnvironment and its
      FunctionsRuntime for user_task_0 of the pinned AgentDojo workspace
      suite.  The task object is returned so callers can access PROMPT,
      GROUND_TRUTH_OUTPUT, and ground_truth() without importing AgentDojo
      directly.

  tool_schemas(runtime)  ->  list[dict]
      Returns the OpenAI-compatible function-call schema list for every
      tool registered in the supplied runtime.  This is the exact list
      passed to the actor at inference time.

Both functions are pure / side-effect free; call environment() fresh for
every episode so no state bleeds across runs.
"""
from blackbox.config import AGENTDOJO_REVISION

SUITE_VERSION = 'v1.2.2'
SUITE_NAME = 'workspace'
TASK_ID = 'user_task_0'

# Pinned to the inspected source revision recorded in blackbox.config.
_EXPECTED_REVISION = AGENTDOJO_REVISION


def _verify_distribution():
    """Raise if the installed AgentDojo package does not match the pinned revision."""
    import importlib.metadata, json
    dist = importlib.metadata.distribution('agentdojo')
    direct = json.loads(dist.read_text('direct_url.json') or '{}')
    commit = direct.get('vcs_info', {}).get('commit_id')
    if commit != _EXPECTED_REVISION:
        raise RuntimeError(
            f'AgentDojo source revision mismatch: want {_EXPECTED_REVISION!r}, '
            f'got {commit!r}.  Install the exact inspected revision.'
        )


def environment(*, verify_revision=True):
    """Return (task, env, runtime) for user_task_0.

    Parameters
    ----------
    verify_revision:
        When True (default), raise if the installed AgentDojo package does not
        match the pinned commit.  Set False only in fast CPU unit tests that
        already check the revision separately.

    Returns
    -------
    task:
        The UserTask0 instance with PROMPT, GROUND_TRUTH_OUTPUT, and
        ground_truth(env) available.
    env:
        A freshly-constructed WorkspaceEnvironment with the task's
        init_environment() applied.  No injection vectors are set.
    runtime:
        A FunctionsRuntime built from the suite's full tool set.
    """
    if verify_revision:
        _verify_distribution()
    from agentdojo.task_suite.load_suites import get_suite
    from agentdojo.functions_runtime import FunctionsRuntime
    suite = get_suite(SUITE_VERSION, SUITE_NAME)
    task = suite.get_user_task_by_id(TASK_ID)
    # Clean environment: no injection payloads applied.
    env = suite.load_and_inject_default_environment({})
    task.init_environment(env)
    runtime = FunctionsRuntime(suite.tools)
    return task, env, runtime


def tool_schemas(runtime):
    """Return the OpenAI-compatible tool schema list for the given runtime.

    This is identical to what NativeTools.schemas() returns; provided here so
    callers that construct the environment outside the full pipeline can still
    obtain the exact schema list without importing pipeline internals.

    Parameters
    ----------
    runtime:
        A FunctionsRuntime (as returned by environment()).

    Returns
    -------
    list[dict] — one entry per tool, in the order the suite registers them.
    """
    return [
        {
            'type': 'function',
            'function': {
                'name': f.name,
                'description': f.description,
                'parameters': f.parameters.model_json_schema(),
            },
        }
        for f in runtime.functions.values()
    ]
