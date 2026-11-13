"""Chat demo: an assistant acting on a simulated mailbox, calendar and drive, guarded by the Wall, laya-cybersec and
the repository's permission memory.

    python -m grids_plugin.app --model qwen2.5:7b --laya-cache /content/hf-cache --memory-store /content/permissions.sqlite --share
"""
import argparse
import json
import time
from pathlib import Path

import gradio as gr

from .memory import MODES as MEMORY_MODES
from .session import ASK_SCENARIOS, MODES, SCENARIOS, VERIFIED_CASES, DemoSession, ask_case, verified_case

HEADERS = ['#', 'Tool', 'Arguments', 'Wall', 'laya-cybersec (ALLOW · ASK · BLOCK)', 'Decision', 'Memory', 'Ran',
           'LLM judge (comparison only)']
GRANT_HEADERS = ['Grant', 'Tool', 'Target', 'Request', 'Uses', 'Expires', 'Active']
INTRO = """
# Permissions That Learn: guarded assistant demo
The assistant works on AgentDojo's **simulated** Workspace (Emma Johnson's mailbox, calendar and drive). Every action it
proposes passes the **Wall** (the user's fixed rules: *only email contacts, never share outside work, never delete*) and
then **laya-cybersec** (322M parameters, on the CPU), which answers **ALLOW, ASK or BLOCK** for whether your request
authorizes the action. With **permission memory** on, "Approve and remember" stores an exact permission, so the same
ask is answered without asking you again. Pick a scenario, a protection level and a memory mode, then send a message.
"""


def seconds(value):
    return f'{value * 1000:.1f} ms' if value < 1 else f'{value:.2f} s'


def compute_markdown(c, laya_on):
    rows = [('Chat model (the assistant)', c['agent_calls'], seconds(c['agent_seconds']), f"{c['agent_tokens']:,} tokens"),
            ('Wall: rules, no model', c['wall_checks'], seconds(c['wall_seconds']), 'includes the recheck before an action runs'),
            ('laya-cybersec, 322M parameters on ' + c['laya_device'].upper(), c['laya_scans'] if laya_on else '-',
             seconds(c['laya_seconds']) if laya_on else '-', 'only for actions the Wall passed; 3 option orders, one call')]
    if c['judge_calls']:
        rows.append(('LLM judge, same checks (comparison only)', c['judge_calls'], seconds(c['judge_seconds']),
                     f"{c['judge_tokens']:,} tokens"))
    table = '| Component | Calls | Time | Note |\n|---|---:|---:|---|\n' + '\n'.join(f'| {a} | {b} | {d} | {e} |' for a, b, d, e in rows)
    notes = [f"**{c['wall_stopped']}** action(s) stopped by the Wall alone, with no model call."]
    if c['judge_calls'] and c['laya_scans']:
        notes.append(f"For the same checks, laya-cybersec took **{seconds(c['laya_seconds'])}** on the CPU; the chat model as "
                     f"judge took **{seconds(c['judge_seconds'])}** and {c['judge_tokens']:,} tokens on the GPU.")
    return '### Compute\n' + table + '\n\n' + ' '.join(notes)


def memory_markdown(session):
    if not session or session.memory is None:
        return '### Permission memory\nOff. Every ask goes to you.'
    m = session.memory_summary()
    return ('### Permission memory\n'
            f"Mode **{MEMORY_MODES[m['mode']]}**. In this session laya-cybersec asked **{m['eligible_asks']}** time(s) that "
            f"memory could answer: **{m['answered_by_grant']}** answered by a remembered permission, "
            f"**{m['asked_person']}** asked you"
            + (f"; the learner would have reused a permission **{m['learner_would_reuse']}** time(s)" if m['mode'] != 'grants' else '')
            + '. File-share confirmations always ask you.')


def pending_markdown(session, waiting):
    if not waiting:
        return ''
    row = session.rows[waiting['action_id']]
    remember = ('You can **approve and remember** it: the same request and action will not ask again.'
                if waiting.get('rememberable') else 'This ask cannot be remembered (a mandatory confirmation, '
                'or memory is off).')
    return (f"### Waiting for your approval\n**{row['tool']}** `{row['arguments']}`\n\nReason: `{row['reason']}`. "
            f'Nothing runs until you decide. {remember}')


def row_markdown(row):
    """What a loaded team dataset row is, before anything runs."""
    call = row['call']
    rebuilt = ('identical to the dataset input' if row['exact'] else
               'not byte-identical to the dataset input (on Windows, run Python in UTF-8 mode)')
    return (f"**Team dataset row {row['id']}** ({row['kind']}). Reviewed label **{row['reviewed_label'] or '-'}**, "
            f"source label {row['source_label'] or '-'}.  \n"
            f"Proposed action: **{call.function}** `{dict(call.args)}`  \n"
            f"Workspace rebuilt with the row's injected text and earlier steps ({rebuilt}); the Wall uses the dataset's "
            "strict preset.")


def case_markdown(case):
    """What an ASK scenario is, before anything runs."""
    call = case['call']
    return (f"**ASK case: {case['id']}** — {case['explain']}  \n"
            f"Request: `{case['prompt']}`  \nAction: **{call.function}** `{dict(call.args)}`  \n"
            "When it waits, press Approve, Approve and remember, or Reject. With learning on, a remembered permission is "
            "reused once the learner has seen it about 10 times (Advanced → memory Grants reuses it at once).")


def row_result_markdown(session):
    """The result of a fixed action, step by step in plain words."""
    r = session.row_result
    if session.error or not r:
        return f'Error: {session.error}' if session.error else 'The action was not run.'
    verified = bool(session.row.get('verified'))
    call = session.row['call']
    steps = [f"**Your request:** {session.row['prompt']}",
             f"**Action being judged:** `{call.function}` `{json.dumps(dict(call.args), ensure_ascii=False)[:200]}`"]
    wall = (r.get('wall') or '-').replace(' (in case)', '')
    if wall == 'off':
        steps.append('**Wall:** off in this pipeline.')
    if wall not in ('PASS', '-', 'off'):
        steps.append(f"**Wall:** stopped it (`{r.get('wall_reason')}`). laya-cybersec was not asked.")
    else:
        if wall != 'off':
            steps.append('**Wall:** passed it' + (' (the verdict recorded in the case).' if verified else '.'))
        if r.get('laya'):
            steps.append(f"**laya-cybersec:** {r['decision']} ({r['laya']}).")
        if r.get('memory') == 'answered by remembered permission':
            steps.append('**Permission memory:** answered it with your remembered permission, so you were **not asked**.')
        elif r.get('asked'):
            answer = {'approved': '**approved** it', 'rejected': '**rejected** it'}.get(r.get('person'), 'did not answer in time')
            remembered = ' and remembered it' if r.get('memory') == 'approved and remembered' else ''
            steps.append(f"**You:** {answer}{remembered}.")
    outcome = ('allowed' if r['executed'] else 'not allowed')
    if verified:
        outcome += ' (verified case: no tool actually runs)'
    else:
        outcome += ', so it ran' if r['executed'] else ', so it did not run'
    steps.append(f"**Result:** {outcome}.")
    if r['attacker_goal_achieved'] is not None:
        steps.append("**Attack check (AgentDojo):** the attacker's goal was "
                     + ('**achieved**.' if r['attacker_goal_achieved'] else '**not achieved**.'))
    expected = session.row.get('reviewed_label')
    if expected:   # dataset rows: the team's reviewed label against the pipeline's decision
        verdict = r['decision'] or '-'
        steps.append(f"**Expected (team's reviewed label):** {expected}. The pipeline decided {verdict}: "
                     + ('**correct**.' if verdict == expected else '**wrong**.'))
    return '\n'.join(f'{i}. {step}' for i, step in enumerate(steps, 1))


def result_message(session, title):
    """The result as its own titled box in the chat, apart from anything the assistant said."""
    return {'role': 'assistant', 'content': row_result_markdown(session), 'metadata': {'title': title}}

USE_PIPELINE = 'Use the pipeline above'
PIPELINES = {'wall_laya': 'Wall + laya-cybersec + learning + memory',
             'laya_only': 'laya-cybersec + learning + memory (no Wall)'}


def build_app(make_session, laya_available=True, memory=None, rows=None):
    """`make_session(mode, scenario, compare, memory_mode, row=None)`; `memory` is the shared Memory store, or None;
    `rows` is a rows.DatasetRows (the team dataset's Workspace rows), or None."""
    modes = [label for key, label in MODES.items() if key not in ('wall_laya', 'laya_only') or laya_available]
    by_label = {label: key for key, label in MODES.items()}
    # The two pipelines on the page; both use laya-cybersec, permission learning and memory. Values are MODES labels.
    pipelines = ([(PIPELINES['wall_laya'], MODES['wall_laya']), (PIPELINES['laya_only'], MODES['laya_only'])] if laya_available
                 else [(MODES['wall_only'], MODES['wall_only'])])
    others = [USE_PIPELINE, MODES['unprotected'], MODES['wall_only']]

    def resolve(mode_label, other=USE_PIPELINE):
        """The protection level: the Advanced choice if one is set, else the pipeline."""
        return by_label[other] if other in by_label else by_label[mode_label]

    def shown(key):
        return PIPELINES.get(key, MODES[key])
    memory_labels = [MEMORY_MODES['off']] + ([label for key, label in MEMORY_MODES.items() if key != 'off'] if memory else [])
    memory_by_label = {label: key for key, label in MEMORY_MODES.items()}

    def grants_view():
        rows = memory.grants() if memory else []
        table = [[g['id'][:8], g['tool'], str(g['target'] or '-')[:60], g['request'][:80], f"{g['uses']}", g['expires'],
                  'yes' if g['active'] else 'no'] for g in rows]
        return table, gr.update(choices=[g['id'][:8] for g in rows if g['active']], value=None)

    def views(session, chat):
        waiting = session.pending if session else None   # read once: the episode thread may change it meanwhile
        pending = bool(waiting)
        rememberable = pending and bool(waiting.get('rememberable'))
        compute = compute_markdown(session.compute(), session.gate is not None) if session else ''
        grants, revoke_choices = grants_view()
        return (chat, session.table() if session else [], compute, pending_markdown(session, waiting), gr.update(interactive=pending),
                gr.update(interactive=rememberable), gr.update(interactive=pending), memory_markdown(session), grants,
                revoke_choices)

    def new_session(mode_label, scenario, compare, memory_label, other=USE_PIPELINE):
        return make_session(resolve(mode_label, other), scenario, compare, memory_by_label.get(memory_label, 'off'))

    def start(mode_label, scenario, compare, memory_label, other=USE_PIPELINE):
        session = new_session(mode_label, scenario, compare, memory_label, other)
        info = (f"**{scenario}** — {SCENARIOS[scenario]['explain']}  \nProtection: **{shown(session.mode)}**. "
                f"Memory: **{MEMORY_MODES[session.memory_mode]}**. Workspace reset; remembered permissions are kept.")
        return (session, [], SCENARIOS[scenario]['prompt'], info, *views(session, [])[1:])

    def send(session, chat, prompt, mode_label, scenario, compare, memory_label, other=USE_PIPELINE):
        if not prompt.strip():
            yield (session, chat, prompt, *views(session, chat)[1:])
            return
        if session is None:
            session = new_session(mode_label, scenario, compare, memory_label, other)
        chat = chat + [{'role': 'user', 'content': prompt}, {'role': 'assistant', 'content': '…working'}]
        thread = session.start(prompt)
        while thread.is_alive():
            yield (session, chat, '', *views(session, chat)[1:])
            time.sleep(0.5)
        chat[-1] = {'role': 'assistant', 'content': session.answers[-1] if not session.error and session.answers
                    else f'Error: {session.error}'}
        yield (session, chat, '', *views(session, chat)[1:])

    def load_row(row_id, mode_label, compare, memory_label, other=USE_PIPELINE):
        from .rows import earlier_steps
        if not row_id:
            raise gr.Error('Pick a dataset row first')
        row = rows.load(row_id)
        session = make_session(resolve(mode_label, other), 'Free chat', compare, memory_by_label.get(memory_label, 'off'),
                               row=row)
        chat = earlier_steps(row['messages'])
        info = (row_markdown(row) + f"  \nProtection: **{shown(session.mode)}**. Memory: **{MEMORY_MODES[session.memory_mode]}**. "
                'Remembered permissions are kept.')
        return (session, chat, row['prompt'], info, *views(session, chat)[1:], gr.update(interactive=True))

    def load_case(name, mode_label, compare, memory_label, other=USE_PIPELINE):
        if not name:
            raise gr.Error('Pick an ASK scenario first')
        case = verified_case(name) if name in VERIFIED_CASES else ask_case(name)
        session = make_session(resolve(mode_label, other), 'Free chat', compare, memory_by_label.get(memory_label, 'off'),
                               row=case)
        info = (case_markdown(case) + f"  \nProtection: **{shown(session.mode)}**. Memory: **{MEMORY_MODES[session.memory_mode]}**. "
                'Workspace reset; remembered permissions are kept.')
        return (session, [], case['prompt'], info, *views(session, [])[1:], gr.update(interactive=True))

    # One list: the team's verified ASK cases, then the team dataset's Workspace rows reviewed as ALLOW or BLOCK
    # (laya-cybersec rarely answers ASK on the dataset's ASK rows, so those are left out; the ASK cases cover asking).
    items = ([(f'ASK case · {name}', f'case:{name}') for name in VERIFIED_CASES]
             + ([(f'Dataset row · {label}', f'row:{row_id}') for label, row_id in rows.choices()
                 if rows.rows[row_id]['reviewed_label'] in ('ALLOW', 'BLOCK')] if rows else []))

    def load_item(item, mode_label, compare, memory_label, other=USE_PIPELINE):
        kind, _, key = (item or '').partition(':')
        if kind == 'row':
            return load_row(key, mode_label, compare, memory_label, other)
        if kind == 'case':
            return load_case(key, mode_label, compare, memory_label, other)
        raise gr.Error('Pick an item first')

    def run_item(item, mode_label, compare, memory_label, other=USE_PIPELINE):
        """One click: load the item (a fresh Workspace) and run its action through the chosen pipeline."""
        session, chat, prompt, info, *rest = load_item(item, mode_label, compare, memory_label, other)
        yield (session, chat, prompt, info, *rest[:-1])
        for update in run_row(session, chat):
            yield (update[0], update[1], prompt, info, *update[2:])

    def run_row(session, chat):
        if session is None or session.row is None:
            raise gr.Error('Press Load first')
        title = f"Result of the action: {session.row['id']}"
        chat = chat + [{'role': 'assistant', 'content': f"…running `{session.row['call'].function}`. If it waits, answer with "
                        'the buttons on the right.', 'metadata': {'title': title}}]
        thread = session.start(session.row['prompt'], recorded=True)
        while thread.is_alive():
            yield (session, chat, *views(session, chat)[1:])
            time.sleep(0.5)
        chat[-1] = result_message(session, title)
        yield (session, chat, *views(session, chat)[1:])

    def decide(session, approved, remember=False):
        if session and session.pending:
            session.respond(approved, remember=remember)
        return gr.update(interactive=False), gr.update(interactive=False), gr.update(interactive=False)

    def revoke(short_id):
        if memory and short_id:
            for g in memory.grants():
                if g['id'].startswith(short_id) and g['active']:
                    memory.revoke(g['id'])
        return grants_view()

    with gr.Blocks(title='GRIDS permission demo') as app:
        state = gr.State(None)
        gr.Markdown(INTRO)
        mode = gr.Radio(pipelines, value=pipelines[0][1], label='Pipeline')
        with gr.Accordion('Test one action: ASK cases and team dataset rows (ALLOW / BLOCK)', open=True):
            gr.Markdown('Pick an item and press **Run**. The result says what the Wall and laya-cybersec decided '
                        '(ALLOW, ASK or BLOCK); when it asks, answer with the buttons on the right. Type to search.'
                        + ('' if rows else ' *(Team dataset rows appear when the demo starts with the dataset token.)*'))
            with gr.Row():
                item_choice = gr.Dropdown(items, value=items[0][1], label='Item', scale=5, filterable=True)
                run_item_button = gr.Button('Run', variant='primary')
        with gr.Accordion('Or chat with the assistant', open=False):
            with gr.Row():
                scenario = gr.Dropdown(list(SCENARIOS), value='Attack only laya-cybersec catches', label='Scenario', scale=4)
                reset = gr.Button('Start / reset Workspace')
        with gr.Accordion('Advanced', open=False):
            with gr.Row():
                other = gr.Radio(others if laya_available else [USE_PIPELINE], value=USE_PIPELINE,
                                 label='Other protection level (instead of the pipeline)')
                memory_mode = gr.Radio(memory_labels, value=MEMORY_MODES['active'] if memory else memory_labels[0],
                                       label='Permission memory', visible=memory is not None)
                compare = gr.Checkbox(False, label='Also time an LLM judge for each check (comparison only)')
        info = gr.Markdown()
        with gr.Row():
            with gr.Column(scale=5):
                chat = gr.Chatbot(label='Assistant', height=430)
                prompt = gr.Textbox(label='Your request', lines=2)
                send_button = gr.Button('Send', variant='primary')
            with gr.Column(scale=6):
                table = gr.Dataframe(headers=HEADERS, label='Every action checked', wrap=True,
                                     column_widths=['4%', '14%', '20%', '10%', '20%', '9%', '11%', '5%', '7%'])
                pending = gr.Markdown()
                with gr.Row():
                    approve = gr.Button('Approve', interactive=False)
                    remember = gr.Button('Approve and remember', interactive=False)
                    reject = gr.Button('Reject', variant='stop', interactive=False)
                compute = gr.Markdown()
                memory_info = gr.Markdown()
                grants = gr.Dataframe(headers=GRANT_HEADERS, label='Remembered permissions', wrap=True,
                                      visible=memory is not None)
                with gr.Row(visible=memory is not None):
                    revoke_choice = gr.Dropdown([], label='Permission to revoke')
                    revoke_button = gr.Button('Revoke')
        outputs = [table, compute, pending, approve, remember, reject, memory_info, grants, revoke_choice]
        buttons = [approve, remember, reject]
        settings = [mode, scenario, compare, memory_mode, other]
        reset.click(start, settings, [state, chat, prompt, info, *outputs])
        run_item_button.click(run_item, [item_choice, mode, compare, memory_mode, other], [state, chat, prompt, info, *outputs])
        send_button.click(send, [state, chat, prompt, *settings], [state, chat, prompt, *outputs])
        approve.click(lambda s: decide(s, True), [state], buttons)
        remember.click(lambda s: decide(s, True, remember=True), [state], buttons)
        reject.click(lambda s: decide(s, False), [state], buttons)
        revoke_button.click(revoke, [revoke_choice], [grants, revoke_choice])
        app.load(start, settings, [state, chat, prompt, info, *outputs])
    return app


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--model', default='qwen2.5:7b', help='Ollama model tag that supports tool calling')
    parser.add_argument('--base-url', default='http://127.0.0.1:11434/v1')
    parser.add_argument('--laya-cache', help='folder for the laya-cybersec download; omit to run without it')
    parser.add_argument('--laya-device', default='cpu', choices=['cpu', 'cuda'])
    parser.add_argument('--memory-store', default=str(Path(__file__).resolve().parents[1] / 'memory' / 'permissions.sqlite'),
                        help="SQLite file for remembered permissions (the repository's PermissionStore)")
    parser.add_argument('--dataset-data', help="folder for the team dataset's files; shows the dataset row picker "
                                                "(the dataset is gated: log in to Hugging Face or set HF_TOKEN)")
    parser.add_argument('--share', action='store_true', help='public gradio.live link (needed on Colab)')
    parser.add_argument('--port', type=int, default=7860)
    args = parser.parse_args(argv)
    scanner = memory = None
    if args.laya_cache:
        from .cybersec import Scanner, download
        from .memory import Memory
        scanner = Scanner(download(args.laya_cache), device=args.laya_device)
        print(f'laya-cybersec loaded in {scanner.load_seconds:.1f} s on {args.laya_device}', flush=True)
        memory = Memory(args.memory_store)
        print(f'Permission memory: {memory.path}', flush=True)

    rows = None
    if args.dataset_data:
        try:
            from .rows import DatasetRows
            rows = DatasetRows(args.dataset_data)
            print(f'Team dataset: {len(rows.rows)} Workspace rows', flush=True)
        except Exception as exc:   # the demo still works without the picker
            print(f'Team dataset not loaded ({type(exc).__name__}: {exc}); the row picker is hidden', flush=True)

    def make_session(mode, scenario, compare, memory_mode, row=None):
        return DemoSession(mode, scenario, scanner, memory=memory, memory_mode=memory_mode, model=args.model,
                           base_url=args.base_url, compare_judge=compare, row=row)

    build_app(make_session, laya_available=scanner is not None, memory=memory, rows=rows).queue().launch(
        share=args.share, server_name='0.0.0.0' if args.share else '127.0.0.1', server_port=args.port)


if __name__ == '__main__':
    main()
