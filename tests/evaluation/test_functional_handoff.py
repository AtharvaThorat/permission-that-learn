"""CPU regressions for failures, trace reports, and explicit actor profiles."""
import json
from pathlib import Path
import threading

import pytest

from experiment.artifacts import atomic
from experiment.aggregate import aggregate
from experiment.report import report
from experiment.scheduler import schedule
from experiment.services import RecordingActor
from experiment.spec import plan
from experiment.store import create_run, Index
from tests.evaluation.test_platform import spec, result


def test_worker_failure_is_durable_and_other_jobs_continue(tmp_path):
    s = spec()
    directory = create_run(s, tmp_path)
    jobs = plan(s)
    def worker(job, attempt, path, queued, cancel):
        if job['mode'] == 'unprotected':
            raise OSError('private provider detail')
        return result(job, attempt, directory)
    schedule(s, jobs, directory, worker)
    summary = aggregate(directory)
    assert summary['attempts'] == 3
    index = json.loads((directory / 'run-index.json').read_text())
    assert [r['status'] for r in index['attempts']].count('infrastructure_error') == 1
    failure = next(directory.glob('episodes/*/*/failure.json'))
    assert json.loads(failure.read_text())['error_kind'] == 'OSError'
    assert 'private provider detail' not in failure.read_text()
    page = Path(report(directory)).read_text(encoding='utf-8')
    assert 'infrastructure_error' in page and 'failure.json' in page


def test_report_preserves_attempts_missing_scores_and_escapes_content(tmp_path):
    s = spec()
    directory = create_run(s, tmp_path)
    job = plan(s)['jobs'][0]
    index = Index(directory)
    attempt, path = index.claim(job)
    atomic(path / 'conversation.json', [{'role': 'assistant', 'content':
        [{'type': 'text', 'content': '<script>alert(1)</script>'}]}])
    index.publish(job, attempt, result(job, attempt, directory, 'pending_approval'))
    index.claim(job, ['pending_approval'])
    index.close()
    before = {p: p.read_bytes() for p in directory.rglob('*') if p.is_file()}
    output = Path(report(directory))
    page = output.read_text(encoding='utf-8')
    assert 'pending_approval' in page and 'interrupted / incomplete' in page and 'not attempted' in page
    assert '&lt;script&gt;' in page and '<script>' not in page
    assert '<h3>Final response</h3><pre>&lt;script&gt;alert(1)&lt;/script&gt;</pre>' in page
    assert 'null' in page and 'conversation.json' in page
    assert all(p.read_bytes() == raw for p, raw in before.items())
    assert Path(report(directory)) != output


def test_failed_actor_response_still_records_payload_exposure(tmp_path):
    from experiment.artifacts import Writer
    class Actor:
        def respond(self, *args):
            raise TimeoutError()
    writer = Writer(tmp_path)
    actor = RecordingActor(Actor(), threading.BoundedSemaphore(1), writer, threading.Event(), 'marker')
    with pytest.raises(TimeoutError):
        actor.respond([{'role': 'tool', 'content': 'marker'}], [], 1)
    writer.close()
    assert actor.exposed
    events = [json.loads(line) for line in (tmp_path / 'actor.jsonl').read_text().splitlines()]
    assert all(e['timestamp'] for e in events)
    assert events[-1]['error'] == 'TimeoutError'


def test_result_publication_failure_is_not_a_success_or_interruption(tmp_path, monkeypatch):
    import experiment.store as store
    s = spec()
    s.modes = ['unprotected']
    directory = create_run(s, tmp_path)
    original = store.atomic
    def fail_result(path, value):
        if Path(path).name == 'result.json':
            raise OSError('simulated full result storage')
        return original(path, value)
    monkeypatch.setattr(store, 'atomic', fail_result)
    schedule(s, plan(s), directory, lambda job, attempt, *args: result(job, attempt, directory))
    summary = aggregate(directory)
    assert summary['metrics'][0]['infrastructure_error'] == 1
    assert summary['metrics'][0]['clean_utility_value'] is None


def test_failure_record_rejects_expired_or_published_attempt(tmp_path):
    s = spec()
    directory = create_run(s, tmp_path)
    job = plan(s)['jobs'][0]
    index = Index(directory)
    try:
        attempt, path = index.claim(job)
        index.db.execute('UPDATE jobs SET expires=0')
        with pytest.raises(RuntimeError, match='Lease lost'):
            index.fail(job, attempt, OSError())
        assert not (path / 'failure.json').exists()
        index.heartbeat()
        index.publish(job, attempt, result(job, attempt, directory))
        before = (path / 'result.json').read_bytes()
        with pytest.raises(RuntimeError, match='Lease lost'):
            index.fail(job, attempt, OSError())
        assert (path / 'result.json').read_bytes() == before
    finally:
        index.close()


def test_missing_native_score_preserves_conversation(tmp_path, monkeypatch):
    from agentdojo.task_suite.task_suite import TaskSuite
    from blackbox.actors.scripted import ScriptedActor
    from blackbox.contracts import Dependencies
    from experiment.runtime import execute
    from tests.blackbox.helpers import reply
    def failure(*args, **kwargs):
        raise ValueError('controlled scoring failure')
    monkeypatch.setattr(TaskSuite, '_check_task_result', failure)
    s = spec()
    s.modes = ['unprotected']
    directory = create_run(s, tmp_path)
    job = plan(s)['jobs'][0]
    index = Index(directory)
    attempt, path = index.claim(job)
    try:
        r = execute(s, None, directory, job, attempt, path, 0, threading.Event(),
                    dependencies=lambda *args: Dependencies(actor=ScriptedActor([reply(content='Done')])))
        index.publish(job, attempt, r)
    finally:
        index.close()
    assert r['utility'] is None and not r['evaluated']
    assert 'native_evaluation_error' in r['backend_errors']
    assert (path / 'conversation.json').exists()
    assert 'infrastructure_error' in Path(report(directory)).read_text()


@pytest.mark.parametrize('name', ['qwen25-7b-t4', 'qwen3-4b-instruct-t4'])
def test_profile_drives_serving_and_single_task_spec(name, tmp_path):
    from scripts.serve_actor import command
    from scripts.functional_smoke import specification
    profile = json.loads((Path('configs/actors') / (name + '.json')).read_text())
    args = command(profile, tmp_path, 8000)
    assert args[args.index('--served-model-name') + 1] == profile['served_model_name']
    assert args[args.index('--tool-call-parser') + 1] == profile['tool_call_parser']
    s = specification(profile, tmp_path, 'user_task_0', ['wall_gatekeeper'], 'http://localhost:8000/v1')
    assert plan(s)['job_count'] == 1
    assert s.actors['functional_actor'].settings.model_revision == profile['revision']
