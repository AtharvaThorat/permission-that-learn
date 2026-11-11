"""Chat demo: an assistant acting on a simulated mailbox, calendar and drive, guarded by the Wall and laya-cybersec.

    python -m grids_plugin.app --model qwen2.5:7b --laya-cache /content/hf-cache --share
"""
import argparse
import time

import gradio as gr

from .session import MODES, SCENARIOS, DemoSession

HEADERS = ['#', 'Tool', 'Arguments', 'Wall', 'laya-cybersec score', 'Decision', 'Ran', 'LLM judge (comparison only)']
INTRO = """
# Permissions That Learn: guarded assistant demo
The assistant works on AgentDojo's **simulated** Workspace (Emma Johnson's mailbox, calendar and drive). Every action it
proposes passes the **Wall** (the user's fixed rules: *only email contacts, never share outside work, never delete*) and
then **laya-cybersec**, a 322M-parameter model on the CPU that checks the action's context for injected instructions.
Pick a scenario and a protection level, then send the message.
"""


def compute_markdown(c, laya_on):
    def seconds(value):
        return f'{value * 1000:.1f} ms' if value < 1 else f'{value:.2f} s'
    rows = [('Chat model (the assistant)', c['agent_calls'], seconds(c['agent_seconds']), f"{c['agent_tokens']:,} tokens"),
            ('Wall: rules, no model', c['wall_checks'], seconds(c['wall_seconds']), 'includes the recheck before an action runs'),
            ('laya-cybersec, 322M parameters on ' + c['laya_device'].upper(), c['laya_scans'] if laya_on else '-',
             seconds(c['laya_seconds']) if laya_on else '-', 'only for actions the Wall passed')]
    if c['judge_calls']:
        rows.append(('LLM judge, same checks (comparison only)', c['judge_calls'], seconds(c['judge_seconds']),
                     f"{c['judge_tokens']:,} tokens"))
    table = '| Component | Calls | Time | Note |\n|---|---:|---:|---|\n' + '\n'.join(f'| {a} | {b} | {d} | {e} |' for a, b, d, e in rows)
    notes = [f"**{c['wall_stopped']}** action(s) stopped by the Wall alone, with no model call."]
    if c['judge_calls'] and c['laya_scans']:
        notes.append(f"For the same checks, laya-cybersec took **{seconds(c['laya_seconds'])}** on the CPU; the chat model as "
                     f"judge took **{seconds(c['judge_seconds'])}** and {c['judge_tokens']:,} tokens on the GPU.")
    return '### Compute\n' + table + '\n\n' + ' '.join(notes)


def pending_markdown(session):
    if not session or not session.pending:
        return ''
    row = session.rows[session.pending['action_id']]
    return (f"### Waiting for your approval\n**{row['tool']}** `{row['arguments']}`\n\nReason: `{row['reason']}`. "
            'Nothing runs until you decide.')


def build_app(make_session, laya_available=True):
    modes = [label for key, label in MODES.items() if key != 'wall_laya' or laya_available]
    by_label = {label: key for key, label in MODES.items()}

    def views(session, chat):
        busy = bool(session and session.pending)
        compute = compute_markdown(session.compute(), session.gate is not None) if session else ''
        return (chat, session.table() if session else [], compute, pending_markdown(session),
                gr.update(interactive=busy), gr.update(interactive=busy))

    def start(mode_label, scenario, compare):
        session = make_session(by_label[mode_label], scenario, compare)
        info = f"**{scenario}** — {SCENARIOS[scenario]['explain']}  \nProtection: **{mode_label}**. Workspace reset."
        return (session, [], SCENARIOS[scenario]['prompt'], info, *views(session, [])[1:])

    def send(session, chat, prompt, mode_label, scenario, compare):
        if not prompt.strip():
            yield (session, chat, prompt, *views(session, chat)[1:])
            return
        if session is None:
            session = make_session(by_label[mode_label], scenario, compare)
        chat = chat + [{'role': 'user', 'content': prompt}, {'role': 'assistant', 'content': '…working'}]
        thread = session.start(prompt)
        while thread.is_alive():
            yield (session, chat, '', *views(session, chat)[1:])
            time.sleep(0.5)
        chat[-1] = {'role': 'assistant', 'content': session.answers[-1] if not session.error and session.answers
                    else f'Error: {session.error}'}
        yield (session, chat, '', *views(session, chat)[1:])

    def decide(session, approved):
        if session and session.pending:
            session.respond(approved)
        return gr.update(interactive=False), gr.update(interactive=False)

    with gr.Blocks(title='GRIDS permission demo') as app:
        state = gr.State(None)
        gr.Markdown(INTRO)
        with gr.Row():
            mode = gr.Radio(modes, value=modes[-1], label='Protection')
            scenario = gr.Dropdown(list(SCENARIOS), value='Attack only laya-cybersec catches', label='Scenario')
            compare = gr.Checkbox(False, label='Also time an LLM judge for each check (comparison only)')
            reset = gr.Button('Start / reset Workspace')
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
                    reject = gr.Button('Reject', variant='stop', interactive=False)
                compute = gr.Markdown()
        outputs = [table, compute, pending, approve, reject]
        reset.click(start, [mode, scenario, compare], [state, chat, prompt, info, *outputs])
        send_button.click(send, [state, chat, prompt, mode, scenario, compare], [state, chat, prompt, *outputs])
        approve.click(lambda s: decide(s, True), [state], [approve, reject])
        reject.click(lambda s: decide(s, False), [state], [approve, reject])
        app.load(start, [mode, scenario, compare], [state, chat, prompt, info, *outputs])
    return app


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--model', default='qwen2.5:7b', help='Ollama model tag that supports tool calling')
    parser.add_argument('--base-url', default='http://127.0.0.1:11434/v1')
    parser.add_argument('--laya-cache', help='folder for the laya-cybersec download; omit to run without it')
    parser.add_argument('--laya-device', default='cpu', choices=['cpu', 'cuda'])
    parser.add_argument('--threshold', type=float, default=0.95)
    parser.add_argument('--share', action='store_true', help='public gradio.live link (needed on Colab)')
    parser.add_argument('--port', type=int, default=7860)
    args = parser.parse_args(argv)
    scanner = None
    if args.laya_cache:
        from .cybersec import Scanner, download
        scanner = Scanner(download(args.laya_cache), device=args.laya_device)
        print(f'laya-cybersec loaded in {scanner.load_seconds:.1f} s on {args.laya_device}')

    def make_session(mode, scenario, compare):
        return DemoSession(mode, scenario, scanner, model=args.model, base_url=args.base_url, threshold=args.threshold,
                           compare_judge=compare)

    build_app(make_session, laya_available=scanner is not None).queue().launch(
        share=args.share, server_name='0.0.0.0' if args.share else '127.0.0.1', server_port=args.port)


if __name__ == '__main__':
    main()
