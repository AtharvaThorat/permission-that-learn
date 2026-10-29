"""Synthetic CPU fixtures only, never performance evidence."""
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import pytest
from grids.core.actions import bind
from grids.core.config import ActorConfig, WallConfig
from grids.core.contracts import Dependencies, Proposal
from grids.actors.client.scripted import ScriptedActor
from grids.core.permissions.ptl_adapter import PtlWall
from grids.benchmarks.agentdojo.context import WorkspaceFacts, Metadata
from grids.benchmarks.agentdojo.tools import NativeTools
from grids.runs.spec import Specification, ActorProfile, plan, load
from grids.runs.artifacts import atomic, Result
from grids.runs.store import create_run, compatible, Index
from grids.runs.aggregate import aggregate
from grids.runs.scheduler import schedule
from grids.runs.runtime import execute
from grids.evaluation.dataset import capture
from grids.evaluation.replay import evaluate
from tests.unit.core.helpers import reply, call, Gate


def spec():
    return Specification(name='fixture', actors={'a':ActorProfile(settings=ActorConfig(),resource_group='gpu0')},
        modes=['unprotected','wall_only','wall_gatekeeper'],clean_tasks=['user_task_0'])


def result(job, attempt, directory, lifecycle='completed'):
    return Result(run_id=directory.name,episode_spec_id=job['episode_spec_id'],attempt_id=attempt,
        pair_id=job['pair_id'],actor_profile=job['actor_profile'],actor=job['actor'],mode=job['mode'],
        identity=job['identity'],suite=job['suite'],task=job['task'],attack=job['attack'],
        repetition=job['repetition'],seed=job['seed'],started_at='2026-01-01T00:00:00Z',ended_at='2026-01-01T00:00:01Z',
        lifecycle=lifecycle,evaluated=lifecycle=='completed',utility=False if lifecycle=='completed' else None,
        counts={},timings_seconds={},actor_usage_coverage={},artifacts={},checksums={}).model_dump()


def test_offline_planning_and_identity(monkeypatch):
    import socket
    monkeypatch.setattr(socket,'create_connection',lambda *a,**k:pytest.fail('network'))
    s=spec(); a=plan(s); assert a==plan(s) and a['job_count']==3
    assert len({j['pair_id'] for j in a['jobs']})==1
    s.budgets.max_actor_turns+=1
    assert plan(s)['jobs'][0]['episode_spec_id']!=a['jobs'][0]['episode_spec_id']
    with pytest.raises(ValueError):Specification(name='empty',actors=s.actors,modes=['unprotected'])


@pytest.mark.parametrize('path',[p for p in Path('configs/experiments').glob('*.json') if p.name != 'authorization.json'])
def test_example_native_pairs(path):
    assert plan(load(path))['job_count']>0






def test_claim_races_stale_and_crash_recovery(tmp_path):
    s=spec(); directory=create_run(s,tmp_path); job=plan(s)['jobs'][0]; a,b=Index(directory),Index(directory)
    try:
        with ThreadPoolExecutor(2) as pool:claims=list(pool.map(lambda index:index.claim(job),(a,b)))
        assert sum(c is not None for c in claims)==1
        owner=a if claims[0] else b; other=b if owner is a else a
        attempt,path=next(c for c in claims if c)
        owner.db.execute('UPDATE jobs SET expires=0'); new=other.claim(job)
        with pytest.raises(RuntimeError,match='Lease lost'):owner.publish(job,attempt,result(job,attempt,directory))
        attempt,path=new; atomic(path/'result.json',result(job,attempt,directory))
        assert other.claim(job) is None and other.snapshot()[-1]['status']=='completed'
        assert aggregate(directory)['attempts']==2
    finally:a.close();b.close()


def test_coordinator_and_resume(tmp_path):
    s=spec(); directory=create_run(s,tmp_path); a,b=Index(directory),Index(directory)
    try:
        a.coordinate()
        with pytest.raises(RuntimeError,match='coordinator'):b.coordinate()
        compatible(directory,s);s.actors['a'].settings.temperature=0.1
        with pytest.raises(ValueError,match='Incompatible'):compatible(directory,s)
    finally:a.close();b.close()


def test_aggregation_missing_failed_and_conflicts(tmp_path):
    s=spec(); directory=create_run(s,tmp_path); jobs=plan(s)['jobs']; index=Index(directory)
    attempt,path=index.claim(jobs[0]);index.publish(jobs[0],attempt,result(jobs[0],attempt,directory))
    attempt2,path2=index.claim(jobs[1]);index.publish(jobs[1],attempt2,result(jobs[1],attempt2,directory,'pending_approval'));index.close()
    summary=aggregate(directory);assert summary['missing']==1
    pending=next(m for m in summary['metrics'] if m['mode']=='wall_only')
    assert pending['clean_utility_value'] is None and pending['reported_total_tokens'] is None
    raw=json.loads((path/'result.json').read_text());raw['mode']='wall_only';atomic(path/'result.json',raw)
    with pytest.raises(ValueError,match='conflict'):aggregate(directory)


def test_scheduler_shared_limits_and_cancellation(tmp_path):
    s=spec();s.seeds=list(range(4));s.limits.global_episodes=3;s.actors['b']=s.actors['a'].model_copy(deep=True)
    s.actors['a'].max_concurrent_requests=2;s.limits.resource_groups={'gpu0':2}
    s.limits.sequential_models=False;s.limits.pending_queue=2
    directory=create_run(s,tmp_path);active=0;peak=0;lock=threading.Lock();counts={};peaks={}
    def worker(job,attempt,path,queued,cancel):
        nonlocal active,peak
        name=job['actor_profile']
        with lock:
            active+=1;peak=max(peak,active);counts[name]=counts.get(name,0)+1;peaks[name]=max(peaks.get(name,0),counts[name])
        time.sleep(.01)
        with lock:active-=1;counts[name]-=1
        return result(job,attempt,directory)
    schedule(s,plan(s),directory,worker)
    assert peak<=2 and peaks['b']<=1 and aggregate(directory)['missing']==0
    cancelled=threading.Event();cancelled.set();directory2=create_run(s,tmp_path)
    schedule(s,plan(s),directory2,lambda *a:pytest.fail('cancelled dispatch'),cancel=cancelled)
    assert aggregate(directory2)['missing']==24


@pytest.mark.parametrize('label,expected',[('ALLOW',1),('ASK',0),('BLOCK',0)])
def test_real_wall_native_runtime_and_replay(tmp_path,label,expected):
    s=spec();directory=create_run(s,tmp_path);jobs=plan(s)['jobs'];index=Index(directory)
    def deps(job,writer):
        return Dependencies(actor=ScriptedActor([reply(call('get_day_calendar_events',{'day':'2024-05-15'})),reply(content='Done')]),
            gatekeeper=Gate((label,)),facts=WorkspaceFacts(Metadata.model_validate(s.metadata)))
    for job in jobs:
        attempt,path=index.claim(job)
        r=execute(s,None,directory,job,attempt,path,0,threading.Event(),dependencies=deps)
        assert r['lifecycle'] in ('completed','pending_approval'),r
        assert r['counts']['dispatches']==(expected if job['mode']=='wall_gatekeeper' else 1)
        index.publish(job,attempt,r)
    index.close();before={p:p.read_bytes() for p in directory.glob('episodes/**/*') if p.is_file()}
    dataset=tmp_path/'dataset'; capture([directory],dataset)
    out=tmp_path/'evaluated'; evaluate(dataset,{'comparators':['wall_only']},out)
    assert json.loads((out/'summary.json').read_text())['records']==3
    assert all(p.read_bytes()==data for p,data in before.items()) and aggregate(directory)['missing']==0


def test_real_wall_binding_and_denials():
    from agentdojo.task_suite.load_suites import get_suite
    from agentdojo.functions_runtime import FunctionsRuntime
    suite=get_suite('v1.2.2','workspace');env=suite.load_and_inject_default_environment({})
    wall=PtlWall.from_clean_environment(WallConfig(implementation='ptl'),env)
    facts=WorkspaceFacts(Metadata.model_validate(spec().metadata))
    action=bind(Proposal('call','delete_file',{'file_id':'13'}),'action',NativeTools(FunctionsRuntime(suite.tools)),facts,wall,env,32000)
    assert wall.evaluate(action).verdict=='DENY'
    assert wall.evaluate(replace(action,state_version='stale')).verdict=='UNRESOLVED'
    assert wall.evaluate(replace(action,policy_version='stale')).verdict=='DENY'


def test_gate_pool_bounded_and_lazy():
    from grids.runs.services import Services
    services=Services(spec());active=0;peak=0;lock=threading.Lock()
    def work(_):
        nonlocal active,peak
        with services.gate(threading.Event()) as gate:
            assert gate.gate is None
            with lock:active+=1;peak=max(peak,active)
            time.sleep(.01)
            with lock:active-=1
    with ThreadPoolExecutor(4) as pool:list(pool.map(work,range(8)))
    services.close();assert peak==1


def test_capture_uses_each_action_state(tmp_path):
    from grids.evaluation.dataset import load_dataset
    s = spec(); s.modes = ['unprotected']
    directory = create_run(s, tmp_path); index = Index(directory)
    def deps(job, writer):
        return Dependencies(actor=ScriptedActor([reply(
            call('create_file', {'filename': 'capture-proof.txt', 'content': 'original'}),
            call('get_current_day', {}, id='call_2')), reply(content='Done')]), gatekeeper=Gate(('ALLOW',)))
    job = plan(s)['jobs'][0]
    attempt, path = index.claim(job)
    value = execute(s, None, directory, job, attempt, path, 0, threading.Event(), dependencies=deps)
    index.publish(job, attempt, value); index.close()
    dataset = tmp_path/'captured'; capture([directory], dataset)
    records = load_dataset(dataset)[1]
    assert len(records) == 2
    assert records[0]['input']['environment'] != records[1]['input']['environment']
    assert 'capture-proof.txt' in json.dumps(records[1]['input']['environment'])


def test_unicode_attempt_identity_round_trip(tmp_path):
    s=spec(); s.actors['a'].settings.served_model_name='\u00e9valuateur'
    directory=create_run(s,tmp_path); index=Index(directory)
    for job in plan(s)['jobs']:
        attempt,path=index.claim(job)
        index.publish(job,attempt,result(job,attempt,directory))
    index.close()
    assert aggregate(directory)['missing']==0
