"""Person 2 baseline report on synthetic run folders; never performance evidence.

The fixture mirrors the layout and field names of a real run folder produced on 2026-10-23 by
`python -m experiment run --config configs/experiments/frozen/unprotected.json` against a local
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


def write_run(root: Path, name: str, utility: bool) -> Path:
    run = root / name
    episode = run / 'episodes' / '3fbfcc0dcd5fa3aa' / '5d372465afe14c5e91f47bafe974475f'
    episode.mkdir(parents=True)
    (run / 'aggregates').mkdir()
    (run / 'plan.json').write_text(json.dumps({'identity': {'implementation': 'ab' * 32}}))
    (run / 'aggregates' / 'summary.json').write_text(json.dumps({'metrics': [{
        'planned': 1, 'completed': 1, 'infrastructure_error': 0, 'clean_utility_value': float(utility),
        'dispatches': 1, 'mean_episode_seconds': 7.76, 'reported_total_tokens': 7366}]}))
    (episode / 'result.json').write_text(json.dumps({
        'task': 'user_task_0', 'lifecycle': 'completed', 'utility': utility, 'pair_id': 'cd' * 32,
        'attempt_id': '5d372465afe14c5e91f47bafe974475f', 'backend_errors': ['native_tool_error'],
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
    return run


def registry(tmp_path: Path) -> Path:
    entries = [
        {'key': 'qwen2.5-7b', 'label': 'Qwen2.5-7B-Instruct', 'model_id': 'Qwen/Qwen2.5-7B-Instruct',
         'source': 'local vLLM', 'frozen': True, 'quantization': 'bitsandbytes-4bit', 'status': 'ran',
         'run_dir': str(write_run(tmp_path, 'frozen-user-task-0-unpro-1', False)), 'error': None},
        {'key': 'qwen3', 'label': 'Qwen3-8B-AWQ', 'model_id': 'Qwen/Qwen3-8B-AWQ', 'source': 'local vLLM',
         'frozen': False, 'quantization': 'awq-4bit', 'status': 'ran',
         'run_dir': str(write_run(tmp_path, 'user-task-0-unprotected-qwen3-1', True)), 'error': None},
        {'key': 'nemotron', 'label': 'Nemotron-3-Nano-4B', 'model_id': 'nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16',
         'source': 'local vLLM', 'frozen': False, 'quantization': None, 'status': 'server_failed',
         'run_dir': None, 'error': 'vLLM exited during startup'},
    ]
    path = tmp_path / 'registry.json'
    path.write_text(json.dumps({'run_info': {'tasks': ['user_task_0'], 'commit': 'abc'}, 'models': entries}))
    return path


def test_report_writes_workbook_csvs_and_three_charts(tmp_path):
    written = report.build_report(registry(tmp_path), tmp_path / 'report')
    assert set(written) == {'summary.csv', 'episodes.csv', 'unprotected_baseline_results.xlsx',
                            '1_task_utility.png', '2_model_activity.png', '3_run_cost.png'}
    workbook = openpyxl.load_workbook(written['unprotected_baseline_results.xlsx'])
    assert workbook.sheetnames == ['Summary', 'Episodes', 'Run info']
    assert workbook['Summary'].max_row == 4 and workbook['Episodes'].max_row == 3


def test_summary_keeps_missing_metrics_empty_and_records_behaviour(tmp_path):
    report.build_report(registry(tmp_path), tmp_path / 'report')
    workbook = openpyxl.load_workbook(tmp_path / 'report' / 'unprotected_baseline_results.xlsx')
    summary = workbook['Summary']
    headers = [cell.value for cell in summary[1]]
    rows = [dict(zip(headers, row)) for row in summary.iter_rows(min_row=2, values_only=True)]
    assert [r['Utility (%)'] for r in rows] == [0, 100, None]
    assert rows[2]['Total tokens'] is None and rows[2]['Problem'] == 'vLLM exited during startup'
    assert rows[0]['Code identity'] == 'ab' * 6
    episodes = workbook['Episodes']
    headers = [cell.value for cell in episodes[1]]
    first = dict(zip(headers, next(episodes.iter_rows(min_row=2, values_only=True))))
    assert first['Tool calls made'] == 'search_calendar_events({"date": "2023-05-26"})'
    assert first['Final answer'] == 'No event found.'


def test_report_never_modifies_run_folders(tmp_path):
    path = registry(tmp_path)
    run_files = sorted(p for p in tmp_path.rglob('*') if p.is_file() and p.name != 'registry.json')
    before = {p: p.read_bytes() for p in run_files}
    report.build_report(path, tmp_path / 'report')
    assert all(p.read_bytes() == content for p, content in before.items())
