"""Chat demo: an assistant acting on a simulated mailbox, calendar and drive, guarded by the Wall, laya-cybersec and
the repository's permission memory.

    python -m grids_plugin.app --model qwen2.5:7b --laya-cache /content/hf-cache --memory-store /content/permissions.sqlite --share
"""
import argparse
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
            f"Workspace rebuilt with the row's injected text and earlier steps ({rebuilt}). Wall: the dataset's strict "
            "preset.  \n**Run the row's action** sends exactly this action through the plugin; when laya-cybersec "
            "answers ASK, you decide. **Send** gives your message to the assistant in this Workspace instead.")


def case_markdown(case):
    """What an ASK scenario is, before anything runs."""
    call = case['call']
    return (f"**ASK scenario: {case['id']}** — {case['explain']}  \n"
            f"Request: `{case['prompt']}`  \nFixed action: **{call.function}** `{dict(call.args)}`  \n"
            "**Run the scenario's action** sends exactly this action "
            + ("to laya-cybersec" if case.get('verified') else "through the Wall and laya-cybersec") + "; when it waits, "
            "press Approve, Approve and remember, or Reject. To see memory at work: Approve and remember, load the same "
            "scenario again and run it: it is answered by the remembered permission. **Send** lets the assistant try instead.")


def row_result_markdown(session):
    r = session.row_result
    if session.error or not r:
        return f'Error: {session.error}' if session.error else 'The row was not run.'
    what = 'Scenario' if session.row.get('suite') is None else 'Row'
    text = (f"{what} {session.row['id']}: **{session.row['call'].function}** — decision **{r['decision'] or '-'}** "
            f"(`{r['reason'] or '-'}`), {'ran' if r['executed'] else 'did not run'}.")
    if r.get('memory'):
        text += f" Memory: {r['memory']}."
    if r.get('decision') == 'ASK' and not r.get('memory'):
        text += ' You were asked.'
    if session.row.get('verified'):
        text += " (Siddharth's case: no tool runs.)"
    if r['attacker_goal_achieved'] is not None:
        text += (" AgentDojo's security check: the attacker's goal was "
                 + ('**achieved**.' if r['attacker_goal_achieved'] else '**not achieved**.'))
    return text


def build_app(make_session, laya_available=True, memory=None, rows=None):
    """`make_session(mode, scenario, compare, memory_mode, row=None)`; `memory` is the shared Memory store, or None;
    `rows` is a rows.DatasetRows (the team dataset's Workspace rows), or None."""
    modes = [label for key, label in MODES.items() if key != 'wall_laya' or laya_available]
    by_label = {label: key for key, label in MODES.items()}
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

    def new_session(mode_label, scenario, compare, memory_label):
        return make_session(by_label[mode_label], scenario, compare, memory_by_label.get(memory_label, 'off'))

    def start(mode_label, scenario, compare, memory_label):
        session = new_session(mode_label, scenario, compare, memory_label)
        info = (f"**{scenario}** — {SCENARIOS[scenario]['explain']}  \nProtection: **{mode_label}**. "
                f"Memory: **{MEMORY_MODES[session.memory_mode]}**. Workspace reset; remembered permissions are kept.")
        return (session, [], SCENARIOS[scenario]['prompt'], info, *views(session, [])[1:])

    def send(session, chat, prompt, mode_label, scenario, compare, memory_label):
        if not prompt.strip():
            yield (session, chat, prompt, *views(session, chat)[1:])
            return
        if session is None:
            session = new_session(mode_label, scenario, compare, memory_label)
        chat = chat + [{'role': 'user', 'content': prompt}, {'role': 'assistant', 'content': '…working'}]
        thread = session.start(prompt)
        while thread.is_alive():
            yield (session, chat, '', *views(session, chat)[1:])
            time.sleep(0.5)
        chat[-1] = {'role': 'assistant', 'content': session.answers[-1] if not session.error and session.answers
                    else f'Error: {session.error}'}
        yield (session, chat, '', *views(session, chat)[1:])

    def load_row(row_id, mode_label, compare, memory_label):
        from .rows import earlier_steps
        if not row_id:
            raise gr.Error('Pick a dataset row first')
        row = rows.load(row_id)
        session = make_session(by_label[mode_label], 'Free chat', compare, memory_by_label.get(memory_label, 'off'), row=row)
        chat = earlier_steps(row['messages'])
        info = (row_markdown(row) + f"  \nProtection: **{mode_label}**. Memory: **{MEMORY_MODES[session.memory_mode]}**. "
                'Remembered permissions are kept.')
        return (session, chat, row['prompt'], info, *views(session, chat)[1:], gr.update(interactive=True))

    def load_case(name, mode_label, compare, memory_label):
        if not name:
            raise gr.Error('Pick an ASK scenario first')
        case = verified_case(name) if name in VERIFIED_CASES else ask_case(name)
        session = make_session(by_label[mode_label], 'Free chat', compare, memory_by_label.get(memory_label, 'off'), row=case)
        info = (case_markdown(case) + f"  \nProtection: **{mode_label}**. Memory: **{MEMORY_MODES[session.memory_mode]}**. "
                'Workspace reset; remembered permissions are kept.')
        return (session, [], case['prompt'], info, *views(session, [])[1:], gr.update(interactive=True))

    def run_row(session, chat):
        if session is None or session.row is None:
            raise gr.Error('Load a dataset row first')
        chat = chat + [{'role': 'assistant', 'content': f"…running the row's action `{session.row['call'].function}`"}]
        thread = session.start(session.row['prompt'], recorded=True)
        while thread.is_alive():
            yield (session, chat, *views(session, chat)[1:])
            time.sleep(0.5)
        chat[-1] = {'role': 'assistant', 'content': row_result_markdown(session)}
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
        with gr.Row():
            mode = gr.Radio(modes, value=modes[-1], label='Protection')
            scenario = gr.Dropdown(list(SCENARIOS), value='Attack only laya-cybersec catches', label='Scenario')
            memory_mode = gr.Radio(memory_labels, value=MEMORY_MODES['grants'] if memory else memory_labels[0],
                                   label='Permission memory', visible=memory is not None)
            compare = gr.Checkbox(False, label='Also time an LLM judge for each check (comparison only)')
            reset = gr.Button('Start / reset Workspace')
        with gr.Accordion('ASK scenarios: laya-cybersec asks you', open=True):
            with gr.Row():
                case_choice = gr.Dropdown(list(VERIFIED_CASES) + list(ASK_SCENARIOS),
                                          value=(list(VERIFIED_CASES) + list(ASK_SCENARIOS))[0], label='ASK scenario', scale=4)
                load_case_button = gr.Button('Load scenario')
                run_case_button = gr.Button("Run the scenario's action", variant='primary', interactive=False)
        with gr.Accordion('Team dataset row (Workspace)', open=False, visible=rows is not None):
            with gr.Row():
                row_choice = gr.Dropdown(rows.choices() if rows else [], label='Row', scale=4)
                load_button = gr.Button('Load row')
                run_row_button = gr.Button("Run the row's action", variant='primary', interactive=False)
        info = gr.Markdown()
        with gr.Row():
            with gr.Column(scale=5):
                chat = gr.Chatbot(label='Assistant', height=430)
                prompt = gr.Textbox(label='Your request', lines=2)
                send_button = gr.Button('Send', variant='primary')
            with gr.Column(scale=6):
                table = gr.Dataframe(headers=HEADERS, label='Every action the assistant proposed', wrap=True)
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
        reset.click(start, [mode, scenario, compare, memory_mode], [state, chat, prompt, info, *outputs]).then(
            lambda: (gr.update(interactive=False), gr.update(interactive=False)), None, [run_row_button, run_case_button])
        load_case_button.click(load_case, [case_choice, mode, compare, memory_mode],
                               [state, chat, prompt, info, *outputs, run_case_button])
        run_case_button.click(run_row, [state, chat], [state, chat, *outputs])
        load_button.click(load_row, [row_choice, mode, compare, memory_mode],
                          [state, chat, prompt, info, *outputs, run_row_button])
        run_row_button.click(run_row, [state, chat], [state, chat, *outputs])
        send_button.click(send, [state, chat, prompt, mode, scenario, compare, memory_mode], [state, chat, prompt, *outputs])
        approve.click(lambda s: decide(s, True), [state], buttons)
        remember.click(lambda s: decide(s, True, remember=True), [state], buttons)
        reject.click(lambda s: decide(s, False), [state], buttons)
        revoke_button.click(revoke, [revoke_choice], [grants, revoke_choice])
        app.load(start, [mode, scenario, compare, memory_mode], [state, chat, prompt, info, *outputs])
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
