from dataclasses import replace
import threading
import pytest
from agentdojo.task_suite.load_suites import get_suite
from agentdojo.functions_runtime import FunctionsRuntime
from blackbox.actions import bind
from blackbox.config import WallConfig
from blackbox.contracts import Proposal, Dependencies
from blackbox.actors.scripted import ScriptedActor
from blackbox.permissions.ptl_adapter import PtlWall
from integrations.agentdojo.tools import NativeTools
from integrations.agentdojo.context import suite_facts, Metadata
from experiment.spec import load, plan
from experiment.store import create_run, Index
from experiment.runtime import execute
from tests.blackbox.helpers import reply, call, Gate


@pytest.mark.parametrize('name,tool', [('slack', 'get_channels'), ('banking', 'get_balance')])
@pytest.mark.parametrize('label', ['ALLOW', 'ASK', 'BLOCK'])
def test_native_suite_shared_controller_and_scoring(tmp_path, name, tool, label):
    spec = load('configs/experiments/frozen/unprotected.json')
    spec.suite, spec.wall.ptl_preset = name, 'STRICT_' + name.upper()
    spec.clean_tasks, spec.attacks = ['user_task_0'], []
    spec.modes = ['unprotected', 'wall_only', 'wall_gatekeeper']
    directory = create_run(spec, tmp_path)
    index = Index(directory)
    try:
        for job in plan(spec)['jobs']:
            attempt, path = index.claim(job)
            def deps(*args):
                return Dependencies(actor=ScriptedActor([reply(call(tool, {})), reply(content='Done')]),
                    gatekeeper=Gate((label,)), facts=suite_facts(name, Metadata.model_validate(spec.metadata)))
            result = execute(spec, None, directory, job, attempt, path, 0, threading.Event(), dependencies=deps)
            assert result['evaluated'], result
            assert result['counts']['dispatches'] == int(job['mode'] != 'wall_gatekeeper' or label == 'ALLOW')
            if job['mode'] == 'wall_gatekeeper' and label == 'ASK':
                assert result['lifecycle'] == 'pending_approval', result['backend_errors']
                assert list((path / 'pending').glob('*.json'))
            index.publish(job, attempt, result)
    finally:
        index.close()


@pytest.mark.parametrize('name', ['workspace', 'slack', 'banking'])
def test_all_native_tools_have_reviewed_effects(name):
    suite = get_suite('v1.2.2', name)
    tools = NativeTools(FunctionsRuntime(suite.tools))
    assert all(tools.effects(tool.name) for tool in suite.tools)


def test_financial_confirmation_and_frozen_payee_identities():
    suite = get_suite('v1.2.2', 'banking')
    env = suite.load_and_inject_default_environment({})
    wall = PtlWall.from_clean_environment(WallConfig(implementation='ptl', ptl_preset='STRICT_BANKING'), env, 'banking')
    tools = NativeTools(FunctionsRuntime(suite.tools))
    facts = suite_facts('banking', Metadata(provenance='test', version='1'))
    args = {'recipient': env.bank_account.transactions[0].recipient, 'amount': 1.0, 'subject': 'test', 'date': '2024-01-01'}
    action = bind(Proposal('call', 'send_money', args), 'action', tools, facts, wall, env, 32000)
    assert wall.evaluate(action).verdict == 'PASS'
    assert wall.evaluate(action).confirmation_required
    assert wall.evaluate(replace(action, state_version='stale')).verdict == 'UNRESOLVED'
    args['recipient'] = 'new-unverified-payee'
    action = bind(Proposal('call', 'send_money', args), 'other', tools, facts, wall, env, 32000)
    assert wall.evaluate(action).verdict != 'PASS'


@pytest.mark.parametrize('suite,task,objective', [('workspace', 'user_task_10', 'injection_task_0'),
    ('slack', 'user_task_0', 'injection_task_1'), ('banking', 'user_task_1', 'injection_task_0')])
def test_native_attack_selection_and_repeat_job_identities(tmp_path, suite, task, objective):
    from scripts.machine_setup import main
    output = tmp_path / 'experiment.json'
    main(['config', '--base', 'configs/experiments/frozen/unprotected.json',
          '--profile', 'configs/actors/qwen25-7b-t4.json', '--profile', 'configs/actors/qwen35-9b-a100.json',
          '--cache-dir', str(tmp_path), '--output', str(output), '--suite', suite, '--task', task,
          '--native-attack', 'direct', '--objective', objective, '--seed', '0', '--seed', '1',
          '--repetitions', '2', '--mode', 'unprotected', '--mode', 'wall_only', '--mode', 'wall_gatekeeper'])
    spec = load(output)
    jobs = plan(spec)['jobs']
    assert len(jobs) == 48
    assert len({job['episode_spec_id'] for job in jobs}) == 48
    assert len({job['pair_id'] for job in jobs}) == 16
    assert spec.attack_panel.startswith('native:direct@')
    from integrations.agentdojo.discovery import materialize
    assert spec.attacks == materialize(suite, 'direct', [task], [objective])


def test_native_arguments_are_not_silently_coerced():
    suite = get_suite('v1.2.2', 'banking')
    tools = NativeTools(FunctionsRuntime(suite.tools))
    with pytest.raises(ValueError, match='MODEL_ARGUMENT_COERCION_REQUIRED'):
        tools.validate('get_most_recent_transactions', {'n': '5'})
    assert tools.validate('get_most_recent_transactions', {'n': 5}) == {'n': 5}


def test_relative_calendar_intent_receives_verified_clock_and_freshness():
    import datetime
    suite = get_suite('v1.2.2', 'workspace')
    env = suite.load_and_inject_default_environment({})
    facts = suite_facts('workspace', Metadata(provenance='test', version='1'))
    before = facts.resolve('get_day_calendar_events', {'day': '2024-05-15'}, env)
    assert before['current_day'] == env.calendar.current_day.isoformat()
    env.calendar.current_day += datetime.timedelta(days=1)
    after = facts.resolve('get_day_calendar_events', {'day': '2024-05-15'}, env)
    assert before['current_day'] != after['current_day']


def test_native_fingerprint_is_stable_across_process_hash_seeds():
    import os
    import subprocess
    import sys
    code = ('from integrations.agentdojo.suites import NativeIdentityContext; '
            'from ptl.wall.models import TargetClass; '
            'print(NativeIdentityContext(account_email="owner@example.org", suite="slack", '
            'native_identities={x:TargetClass.CONTACT for x in {"alice","bob"}}, '
            'native_resources={"channel":{"team":frozenset({"alice","bob"})}}).fingerprint())')
    outputs = [subprocess.check_output([sys.executable, '-c', code],
               env={**os.environ, 'PYTHONHASHSEED': seed}, text=True).strip() for seed in ('1', '987')]
    assert outputs[0] == outputs[1]
