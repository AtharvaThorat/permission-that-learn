"""The environment replay on three rows from the repository's published copy (no Hugging Face login needed)."""
import json
import os
import sys

from support import FakeScanner

from grids.gatekeeper import training_data as td
from grids_plugin import replay as rp
from grids_plugin.evaluate import reviewed_labels

IDS = ('GRIDS_115', 'GRIDS_176', 'GRIDS_199')   # Slack injected goal, Slack Wall DENY, Banking read the user asked for
# On Windows, AgentDojo reads its files in the right encoding only in UTF-8 mode (as the module's command line requires).
EXACT = os.name != 'nt' or sys.flags.utf8_mode


def inputs():
    published = td.Layout().published
    references = {r['source_id']: r for split in ('train', 'test') for r in td.read_jsonl(published / f'{split}.jsonl')}
    rows = [{'id': r['id'], 'source_id': r['source_id'], 'source_label': r['label']}
            for r in references.values() if r['id'] in IDS]
    provenance = {r['id']: r for r in td.read_jsonl(published / 'provenance.jsonl')}
    labels = {i: r['reviewed_label'] for i, r in reviewed_labels().items()}
    return rows, references, labels, provenance


def test_parse_source_ids():
    goal = rp.parse('agentdojo:v1.2.2/slack/user_task_2/pv012/injection_task_3/important_instructions')
    assert goal == {'suite': 'slack', 'task': 'user_task_2', 'neuralchemy': None, 'injection': 'injection_task_3',
                    'variant': 'pv012', 'kind': 'goal', 'template': 'important_instructions'}
    call = rp.parse('agentdojo:v1.2.2/banking/user_task_1/call3/injection_task_6/neuralchemy+neuralchemy:core/train/9:ab')
    assert (call['kind'], call['k'], call['injection'], call['template']) == ('call', 3, 'injection_task_6', 'neuralchemy')
    assert call['neuralchemy'] == 'neuralchemy:core/train/9:ab'
    mismatch = rp.parse('agentdojo:v1.2.2/slack/user_task_0/mismatch/user_task_4/call2')
    assert (mismatch['kind'], mismatch['other'], mismatch['j']) == ('mismatch', 'user_task_4', 2)


def test_rows_replay_through_the_plugin(tmp_path):
    rows, references, labels, provenance = inputs()
    summary = rp.replay(rows, references, labels, provenance, FakeScanner(), tmp_path / 'run', log=lambda _: None)
    records = {r['id']: r for r in map(json.loads, (tmp_path / 'run' / 'records.jsonl').read_text().splitlines())}
    if EXACT:
        assert summary['environment_exact'] == 3
    assert summary['wall_matches_recorded'] == 3
    assert records['GRIDS_176']['outcome'] == 'stopped by the Wall' and records['GRIDS_176']['wall'] == 'DENY'
    goal = records['GRIDS_115']
    assert goal['kind'] == 'injected goal' and not goal['executed'] and goal['attacker_goal_achieved'] is False
    allowed = records['GRIDS_199']
    assert (allowed['wall'], allowed['gate'], allowed['outcome']) == ('PASS', 'ALLOW', 'ran without asking')
    assert summary['block_labelled_ran_without_person'] == 0
    assert (tmp_path / 'run' / 'report.md').is_file()


def test_remembered_ask_is_answered_in_the_second_pass(tmp_path):
    rows, references, labels, provenance = inputs()
    rows = [r for r in rows if r['id'] == 'GRIDS_199']
    labels['GRIDS_199'] = 'ASK'   # the careful person approves and remembers
    summary = rp.replay(rows, references, labels, provenance, FakeScanner(ask_tools={'get_most_recent_transactions'}),
                        tmp_path / 'run', log=lambda _: None)
    first, second = map(json.loads, (tmp_path / 'run' / 'records.jsonl').read_text().splitlines())
    assert (first['pass'], first['outcome'], first['remembered']) == (1, 'person approved, ran', True)
    assert (second['pass'], second['outcome'], second['asked_person']) == (2, 'ran on a remembered permission', False)
    assert summary['memory'] == {'remembered_in_pass_1': 1, 'repeated_in_pass_2': 1, 'answered_by_grant': 1,
                                 'grant_ran_block_labelled': 0}
