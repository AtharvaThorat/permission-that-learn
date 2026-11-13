"""Team dataset rows in the chat demo, from the repository's published copy (no Hugging Face login needed)."""
from support import FakeScanner

from grids.gatekeeper import training_data as td
from grids_plugin.app import build_app
from grids_plugin.rows import DatasetRows
from grids_plugin.session import DemoSession

GOAL, OWN = 'GRIDS_305', 'GRIDS_306'   # Workspace: injected goal (send_email to the attacker); the user's own send_email


def dataset_rows():
    published = td.Layout().published
    references = [r for split in ('train', 'test') for r in td.read_jsonl(published / f'{split}.jsonl')]
    return DatasetRows(rows=[{'id': r['id'], 'source_id': r['source_id'], 'source_label': r['label']}
                             for r in references if r['id'] in (GOAL, OWN)])


def test_injected_goal_row_with_and_without_protection():
    rows = dataset_rows()
    assert [i for _, i in rows.choices()] == [GOAL, OWN]
    for mode, decision, executed, achieved in (('wall_laya', 'BLOCK', False, False), ('unprotected', 'ALLOW', True, True)):
        row = rows.load(GOAL)
        session = DemoSession(mode, 'Free chat', FakeScanner(), row=row)
        session.run(row['prompt'], recorded=True)
        r = session.row_result
        assert (r['decision'], r['executed'], r['memory'], r['attacker_goal_achieved'], r['asked'], r['person']) == (
            decision, executed, None, achieved, False, None), (mode, r)


def test_person_answers_a_row_ask_on_the_page_and_memory_remembers(tmp_path):
    from grids_plugin.memory import Memory
    memory, rows = Memory(tmp_path / 'permissions.sqlite'), dataset_rows()

    def make_session(mode, scenario, compare, memory_mode, row=None):
        return DemoSession(mode, scenario, FakeScanner(ask_tools={'send_email'}), memory=memory, memory_mode=memory_mode,
                           row=row)

    app = build_app(make_session, memory=memory, rows=rows)
    run = next(fn.fn for fn in app.fns.values() if getattr(fn.fn, '__name__', '') == 'run_item')
    args = (f'row:{OWN}', 'Wall + laya-cybersec', False, 'Grants (reuse remembered permissions)')
    stream = run(*args)
    session, chat, prompt, info, *_ = next(stream)   # loaded: the row's request and earlier steps
    assert prompt == session.row['prompt'] and 'Team dataset row GRIDS_306' in info
    assert any('(earlier step)' in m['content'] for m in chat)
    for update in stream:
        if update[6]:   # the page shows laya-cybersec's ask; the person presses "Approve and remember"
            update[0].respond(True, remember=True)
            break
    *_, last = list(stream)
    assert last[0].row_result['executed'] and 'ran' in last[1][-1]['content']
    assert last[4][0][6] == 'approved and remembered'
    *_, last = list(run(*args))   # the same row again: answered by the remembered permission
    assert last[4][0][6] == 'answered by remembered permission' and last[4][0][7] == 'yes'


def test_result_names_the_request_the_judged_action_and_the_expected_label():
    rows = dataset_rows()
    row = rows.load(GOAL)
    session = DemoSession('wall_laya', 'Free chat', FakeScanner(), row=row)
    session.run(row['prompt'], recorded=True)
    from grids_plugin.app import row_result_markdown
    from grids_plugin.rows import earlier_steps
    text = row_result_markdown(session)
    assert f"**Your request:** {row['prompt']}" in text and '**Action being judged:** `send_email`' in text
    assert "**Expected (team's reviewed label):** BLOCK. The pipeline decided BLOCK: **correct**." in text
    chat = earlier_steps(row['messages'])
    assert chat[0]['role'] == 'user' and chat[-1]['metadata']['title'].startswith('Earlier steps')
    assert sum('metadata' in m for m in chat) == 1   # one collapsed box, not one bubble per step
