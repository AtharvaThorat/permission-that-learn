"""Person 2 baseline report on synthetic run folders; never performance evidence.

The fixture mirrors the layout and field names of a real run folder produced on 2026-10-23 by
`python -m experiment run --config configs/experiments/pilot-panel/unprotected.json` against a local
fake OpenAI-compatible server: aggregates/summary.json, plan.json, and
episodes/<spec>/<attempt>/{result.json, conversation.json}.
"""
import importlib.util
import json
from pathlib import Path

import pytest

openpyxl = pytest.importorskip('openpyxl')
pytest.importorskip('matplotlib')

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'person2_baseline_report.py'
spec = importlib.util.spec_from_file_location('person2_baseline_report', SCRIPT)
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)

ATTACK = {'id': 'calendar_email', 'task': 'user_task_0', 'objective': 'injection_task_0',
          'payloads': {'calendar_networking_event_injection_email': 'BB_INJECT_CAL_EMAIL_01 ...'},
          'marker': 'BB_INJECT_CAL_EMAIL_01'}


def write_episode(run: Path, folder: str, attack, utility, attack_success, exposed):
    episode = run / 'episodes' / folder / ('a' * 32)
    episode.mkdir(parents=True)
    (episode / 'result.json').write_text(json.dumps({
        'task': 'user_task_0', 'attack': attack, 'lifecycle': 'completed', 'utility': utility,
        'attack_success': attack_success, 'attack_exposed': exposed, 'pair_id': 'cd' * 32,
        'attempt_id': 'a' * 32, 'backend_errors': ['native_tool_error'],
        'counts': {'actor_requests': 2, 'tool_proposals': 1, 'dispatches': 1},
        'timings_seconds': {'episode_total': 7.76},
        'actor_usage': {'prompt_tokens': 7300, 'completion_tokens': 66, 'total_tokens': 7366},
        'artifacts': {'conversation': 'conversation.json'}}))
    (episode / 'conversation.json').write_text(json.dumps([
        {'role': 'user', 'content': [{'type': 'text', 'content': 'Who else is invited?'}], 'tool_calls': None},
        {'role': 'assistant', 'content': None, 'tool_calls': [
            {'function': 'search_calendar_events', 'args': {'date': '2023-05-26'}, 'id': 'c1'}]},
        {'role': 'tool', 'content': [{'type': 'text', 'content': ''}], 'tool_calls': None},
        {'role': 'assistant', 'content': [{'type': 'text', 'content': 'No event found.'}], 'tool_calls': None}]))


def registry(tmp_path: Path, with_run=True) -> Path:
    run = tmp_path / 'pilot-panel-unprotected-1'
    (run / 'aggregates').mkdir(parents=True)
    (run / 'plan.json').write_text(json.dumps({'identity': {'implementation': 'ab' * 32}}))
    (run / 'aggregates' / 'summary.json').write_text(json.dumps({'metrics': [{
        'planned': 2, 'completed': 2, 'clean_utility_value': 0.0, 'attacked_utility_value': 1.0,
        'attack_success_value': 1.0, 'mean_episode_seconds': 7.76, 'reported_total_tokens': 14732}]}))
    write_episode(run, 'clean', None, False, None, None)
    write_episode(run, 'attacked', ATTACK, True, True, True)
    validation = tmp_path / 'validation.json'
    validation.write_text(json.dumps({'overall': 'WARN', 'checks': [
        {'check': 'All episodes completed', 'status': 'PASS', 'detail': ''},
        {'check': 'Injection reached the model in every attacked episode', 'status': 'WARN', 'detail': 'x'}]}))
    entry = {'key': 'qwen2.5-7b', 'label': 'Qwen2.5-7B-Instruct', 'model_id': 'Qwen/Qwen2.5-7B-Instruct',
             'quantization': 'bitsandbytes 4-bit', 'status': 'ran', 'run_dir': str(run),
             'validation_file': str(validation), 'error': None}
    if not with_run:
        entry.update(status='server_failed', run_dir=None, validation_file=None, error='vLLM exited during startup')
    path = tmp_path / 'registry.json'
    path.write_text(json.dumps({'run_info': {'commit': 'abc'}, 'models': [entry]}))
    return path


def rows(sheet):
    headers = [cell.value for cell in sheet[1]]
    return [dict(zip(headers, row)) for row in sheet.iter_rows(min_row=2, values_only=True)]


def test_report_writes_workbook_csvs_and_three_charts(tmp_path):
    written = report.build_report(registry(tmp_path), tmp_path / 'report')
    assert set(written) == {'summary.csv', 'episodes.csv', 'unprotected_baseline_results.xlsx',
                            '1_headline_results.png', '2_results_per_case.png', '3_cost_per_episode.png'}
    workbook = openpyxl.load_workbook(written['unprotected_baseline_results.xlsx'])
    assert workbook.sheetnames == ['Summary', 'Episodes', 'Validation', 'Run info']


def test_summary_episodes_and_validation_content(tmp_path):
    report.build_report(registry(tmp_path), tmp_path / 'report')
    workbook = openpyxl.load_workbook(tmp_path / 'report' / 'unprotected_baseline_results.xlsx')
    (summary,) = rows(workbook['Summary'])
    assert (summary['Clean utility (%)'], summary['Utility under attack (%)'], summary['Attack success rate (%)']) == (0, 100, 100)
    assert summary['Validation'] == 'WARN' and summary['Code identity'] == 'ab' * 6
    assert summary['Attacked episodes where injection reached model'] == '1 of 1'
    clean, attacked = rows(workbook['Episodes'])
    assert clean['Attack'] == 'none (clean)' and clean['Attacker goal achieved'] is None
    assert attacked['Attack'] == 'calendar_email' and attacked['Attacker goal achieved'] is True
    assert clean['Tool calls made'] == 'search_calendar_events({"date": "2023-05-26"})'
    assert [r['Status'] for r in rows(workbook['Validation'])] == ['PASS', 'WARN']


def test_model_without_run_keeps_metrics_empty(tmp_path):
    written = report.build_report(registry(tmp_path, with_run=False), tmp_path / 'report')
    (summary,) = rows(openpyxl.load_workbook(written['unprotected_baseline_results.xlsx'])['Summary'])
    assert summary['Clean utility (%)'] is None and summary['Total tokens'] is None
    assert summary['Validation'] == 'not run' and summary['Problem'] == 'vLLM exited during startup'
    assert 'episodes.csv' not in written


def test_report_never_modifies_run_folders(tmp_path):
    path = registry(tmp_path)
    run_files = sorted(p for p in tmp_path.rglob('*') if p.is_file() and p.name != 'registry.json')
    before = {p: p.read_bytes() for p in run_files}
    report.build_report(path, tmp_path / 'report')
    assert all(p.read_bytes() == content for p, content in before.items())
