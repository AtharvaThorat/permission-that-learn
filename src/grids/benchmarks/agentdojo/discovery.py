"""Native discovery and deterministic native attack materialization; no actors."""
from types import SimpleNamespace

SUPPORTED_ATTACKS = ('direct', 'ignore_previous', 'system_message', 'injecagent')
SUITES = ('workspace', 'slack', 'banking')


def discover(name):
    from agentdojo.task_suite.load_suites import get_suite
    from .tools import NativeTools
    from agentdojo.functions_runtime import FunctionsRuntime
    suite = get_suite('v1.2.2', name)
    tools = NativeTools(FunctionsRuntime(suite.tools))
    return {'suite': name, 'user_tasks': {key: task.PROMPT for key, task in suite.user_tasks.items()},
            'attack_objectives': {key: task.GOAL for key, task in suite.injection_tasks.items()},
            'native_attack_templates': list(SUPPORTED_ATTACKS),
            'injection_vectors': sorted(suite.get_injection_vector_defaults()),
            'tools': {tool.name: {'effects': tools.effects(tool.name),
                                 'schema': tool.parameters.model_json_schema()} for tool in suite.tools}}


def materialize(name, attack_name, tasks, objectives):
    from agentdojo.task_suite.load_suites import get_suite
    from agentdojo.attacks import load_attack
    from grids.runs.spec import Attack
    if attack_name not in SUPPORTED_ATTACKS:
        raise ValueError('Native attack template not supported by the offline preparation workflow')
    suite = get_suite('v1.2.2', name)
    attack = load_attack(attack_name, suite, SimpleNamespace(name='offline-materialization'))
    records = []
    for task in tasks:
        for objective in objectives:
            payloads = attack.attack(suite.get_user_task_by_id(task), suite.get_injection_task_by_id(objective))
            records.append(Attack(id=f'{attack_name}-{task}-{objective}', task=task,
                                  objective=objective, payloads=dict(payloads), native_template=attack_name))
    return records
