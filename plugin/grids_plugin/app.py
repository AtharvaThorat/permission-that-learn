"""Chat demo: an assistant acting on a simulated mailbox, calendar and drive, guarded by the Wall, laya-cybersec and
the repository's permission memory.

    python -m grids_plugin.app --model qwen2.5:7b --laya-cache /content/hf-cache --memory-store /content/permissions.sqlite --share
"""
import argparse
import json
import random
import time
from pathlib import Path

import gradio as gr

from .learner import APPROVED as LEARNER_APPROVED, STOPPED as LEARNER_STOPPED
from .look import CSS, HOW_IT_WORKS, THEME, hero, stage_html
from .memory import MODES as MEMORY_MODES
from .session import (ASK_SCENARIOS, MODES, SCENARIOS, VERIFIED_CASES, DemoSession, ask_case, borderline, case_label,
                      verified_case)

HEADERS = ['#', 'Tool', 'Arguments', 'Wall', 'laya-cybersec (ALLOW · ASK · BLOCK)', 'Decision', 'Memory', 'Ran',
           'LLM judge (comparison only)']
GRANT_HEADERS = ['Grant', 'Tool', 'Target', 'Request', 'Uses', 'Expires', 'Active']
QUICK = (('email', '📧  Try an email search'), ('calendar', '📅  Try a calendar search'), ('files', '📁  Try opening a file'))


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


def learner_markdown(learner):
    """What Atharva's learner has learned, one row per kind of request."""
    text = ("### Permission memory: Atharva's learner\n"
            f"**Approve and remember** counts as one approval of that **kind** of request (the same tool, reaching the "
            f"same kinds of people). After **{learner.k}** approvals of a kind with no rejection, a new request of that "
            "kind is approved **without asking**. One **Reject** stops that kind without asking. A plain **Approve** "
            "allows it once and teaches nothing. File-share confirmations always ask you.\n\n")
    kinds = learner.kinds()
    if not kinds:
        return text + 'Nothing learned yet.'
    state = {'learning': 'asks you', 'learned': '⚡ approves new ones', 'stopped': '✕ stops new ones'}
    rows = '\n'.join(f"| `{k['tool']}` | {k['reaches']} | {min(k['approvals'], learner.k)} of {learner.k} | {k['rejections']} | "
                     f"{state[k['state']]} | {'; '.join(r[:60] for r in k['requests'][-3:])} |" for k in kinds)
    return (text + '| Kind (tool) | Reaches | Approvals | Rejections | Now | Learned from (latest) |\n'
            '|---|---|---|---|---|---|\n' + rows)


def memory_markdown(session):
    if session is not None and getattr(session, 'learner', None) is not None:
        return learner_markdown(session.learner)
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
    if waiting.get('key') and session.learner is not None:   # Atharva's learner
        approvals, _ = session.learner.progress(waiting['key'])
        remember = (f"**Approve and remember** teaches the learner: {approvals} of {session.learner.k} approvals of this "
                    f"kind so far. After {session.learner.k}, new requests of this kind are approved without asking. "
                    "**Approve** allows it just this once; **Reject** stops this kind.")
    if waiting.get('remembered'):
        remember = (f"**Already remembered** (permission `{waiting['remembered'][:8]}`), so **Approve** is enough. "
                    f"Memory mode **{MEMORY_MODES[session.memory_mode]}** decides when it answers without asking.")
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
        elif r.get('memory') == LEARNER_APPROVED:
            steps.append("**Atharva's learner:** you approved enough requests of this kind before, so it approved this "
                         'one and you were **not asked**.')
        elif r.get('memory') == LEARNER_STOPPED:
            steps.append("**Atharva's learner:** you rejected this kind before, so it stopped this one and you were "
                         '**not asked**.')
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


def build_app(make_session, laya_available=True, memory=None, rows=None, learner=None):
    """`make_session(mode, scenario, compare, memory_mode, row=None)`; `memory` is the shared Memory store, or None;
    `rows` is a rows.DatasetRows (the team dataset's Workspace rows), or None; `learner` is Atharva's learner
    (learner.Learner), the page's permission memory when given (memory is then None)."""
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
    memory_labels = ([MEMORY_MODES['learner']] if learner else
                     [MEMORY_MODES['off']] + ([label for key, label in MEMORY_MODES.items() if key not in ('off', 'learner')]
                                              if memory else []))
    memory_by_label = {label: key for key, label in MEMORY_MODES.items()}

    def grants_view():
        rows = memory.grants() if memory else []
        table = [[g['id'][:8], g['tool'], str(g['target'] or '-')[:60], g['request'][:80], f"{g['uses']}", g['expires'],
                  'yes' if g['active'] else 'no'] for g in rows]
        return table, gr.update(choices=[g['id'][:8] for g in rows if g['active']], value=None)

    def views(session, chat):
        waiting = session.pending if session else None   # read once: the episode thread may change it meanwhile
        pending = bool(waiting)
        rememberable = pending and bool(waiting.get('rememberable')) and not waiting.get('remembered')
        compute = compute_markdown(session.compute(), session.gate is not None) if session else ''
        grants, revoke_choices = grants_view()
        return (chat, session.table() if session else [], compute, pending_markdown(session, waiting), gr.update(interactive=pending),
                gr.update(interactive=rememberable), gr.update(interactive=pending), memory_markdown(session), grants,
                revoke_choices, stage_html(session))

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
    row_items = ([(f'Dataset row · {label}', f'row:{row_id}') for label, row_id in rows.choices()
                  if rows.rows[row_id]['reviewed_label'] in ('ALLOW', 'BLOCK')] if rows else [])
    items = [(case_label(case), f'case:{name}') for name, case in VERIFIED_CASES.items()] + row_items
    # The same list by category, for the filter above it.
    groups = {f'All ({len(items)})': items}
    for keys, title in ((('email',), 'Email'), (('calendar',), 'Calendar'), (('files',), 'Files'),
                        (('slack', 'banking'), 'Slack & Banking')):
        members = [(case_label(c), f'case:{name}') for name, c in VERIFIED_CASES.items() if c['category'] in keys]
        if members:
            groups[f'{title} ({len(members)})'] = members
    if row_items:
        groups[f'Team dataset rows ({len(row_items)})'] = row_items
    # Quick starts use the first case of each category that the plugin's method answers with ASK.
    quick = [(text, f'case:{first}') for category, text in QUICK
             if (first := next((n for n, c in VERIFIED_CASES.items() if c['category'] == category and not borderline(n)), None))]

    def filter_items(group):
        choices = groups.get(group) or items
        return gr.update(choices=choices, value=choices[0][1] if choices else None)

    def pick_random(group):
        return random.choice(groups.get(group) or items)[1]

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

    with gr.Blocks(title='Permissions That Learn: guarded assistant demo') as app:
        state = gr.State(None)
        gr.HTML(hero(len(VERIFIED_CASES), len(row_items)))
        with gr.Row(elem_classes='quick'):
            quick_buttons = [(gr.Button(text, size='lg'), value) for text, value in quick]
            surprise = gr.Button('🎲  Surprise me', size='lg', variant='secondary')
        with gr.Row(equal_height=False, elem_classes='main-row'):
            with gr.Column(scale=4, elem_classes='panel'):
                gr.Markdown('### <span>1</span>Choose an action to test', elem_classes='step-title')
                category = gr.Radio(list(groups), value=next(iter(groups)), show_label=False, elem_classes='pills')
                item_choice = gr.Dropdown(items, value=items[0][1] if items else None, label='Action to test',
                                          filterable=True, info='Type to search by request, category or id.'
                                          + ('' if rows else ' Team dataset rows appear when the demo starts with the dataset token.'))
                run_item_button = gr.Button('▶  Run it through the guard', variant='primary', size='lg')
                gr.Markdown('### <span>2</span>Choose the protection', elem_classes='step-title')
                mode = gr.Radio(pipelines, value=pipelines[0][1], show_label=False)
                with gr.Accordion('About this action', open=False):
                    info = gr.Markdown()
                with gr.Accordion('Advanced settings', open=False):
                    other = gr.Radio(others if laya_available else [USE_PIPELINE], value=USE_PIPELINE,
                                     label='Other protection level (instead of the pipeline)')
                    memory_mode = gr.Radio(memory_labels, value=MEMORY_MODES['active'] if memory else memory_labels[0],
                                           label='Permission memory', visible=memory is not None)
                    compare = gr.Checkbox(False, label='Also time an LLM judge for each check (comparison only)')
            with gr.Column(scale=7):
                stage = gr.HTML(stage_html(None))
                with gr.Column(elem_classes='approval'):
                    gr.Markdown('#### ✋ Your decision\nThese buttons light up when the guard asks you. Nothing runs until '
                                'you choose.')
                    pending = gr.Markdown()
                    with gr.Row():
                        approve = gr.Button('✓  Approve', interactive=False, elem_classes='approve-btn')
                        remember = gr.Button('★  Approve and remember', interactive=False, elem_classes='remember-btn')
                        reject = gr.Button('✕  Reject', interactive=False, elem_classes='reject-btn')
        with gr.Tabs():
            with gr.Tab('📋 Every action checked'):
                table = gr.Dataframe(headers=HEADERS, label='Every action checked', wrap=True,
                                     column_widths=['4%', '14%', '20%', '10%', '20%', '9%', '11%', '5%', '7%'])
            with gr.Tab('⚡ Compute'):
                compute = gr.Markdown()
            with gr.Tab('🗂️ Permission memory'):
                memory_info = gr.Markdown()
                grants = gr.Dataframe(headers=GRANT_HEADERS, label='Remembered permissions', wrap=True,
                                      visible=memory is not None)
                with gr.Row(visible=memory is not None):
                    revoke_choice = gr.Dropdown([], label='Permission to revoke')
                    revoke_button = gr.Button('Revoke')
                forget = gr.Button('↺  Forget what the learner learned', visible=learner is not None)
            with gr.Tab('💬 Chat with the assistant'):
                gr.Markdown('Results of **Run** also appear here. To chat, pick a scenario, reset the Workspace and send a '
                            'request (needs the chat model on Ollama).')
                with gr.Row():
                    scenario = gr.Dropdown(list(SCENARIOS), value='Attack only laya-cybersec catches', label='Scenario', scale=4)
                    reset = gr.Button('Start / reset Workspace')
                chat = gr.Chatbot(label='Assistant', height=430)
                prompt = gr.Textbox(label='Your request', lines=2)
                send_button = gr.Button('Send', variant='primary')
            with gr.Tab('ℹ️ How it works'):
                gr.Markdown(HOW_IT_WORKS)
        outputs = [table, compute, pending, approve, remember, reject, memory_info, grants, revoke_choice, stage]
        buttons = [approve, remember, reject]
        settings = [mode, scenario, compare, memory_mode, other]
        run_inputs = [item_choice, mode, compare, memory_mode, other]
        run_outputs = [state, chat, prompt, info, *outputs]
        # Streaming events show their progress in the pipeline view, so Gradio's loading overlays are hidden.
        quiet = {'show_progress': 'hidden'}
        reset.click(start, settings, [state, chat, prompt, info, *outputs], **quiet)
        run_item_button.click(run_item, run_inputs, run_outputs, **quiet)
        category.change(filter_items, [category], [item_choice])
        for button, value in quick_buttons:
            button.click(lambda value=value: value, None, [item_choice]).then(run_item, run_inputs, run_outputs, **quiet)
        surprise.click(pick_random, [category], [item_choice]).then(run_item, run_inputs, run_outputs, **quiet)
        send_button.click(send, [state, chat, prompt, *settings], [state, chat, prompt, *outputs], **quiet)
        approve.click(lambda s: decide(s, True), [state], buttons)
        remember.click(lambda s: decide(s, True, remember=True), [state], buttons)
        reject.click(lambda s: decide(s, False), [state], buttons)
        revoke_button.click(revoke, [revoke_choice], [grants, revoke_choice])

        def forget_learned(session):
            if learner is not None:
                learner.forget()
            return memory_markdown(session)

        forget.click(forget_learned, [state], [memory_info])
        app.load(start, settings, [state, chat, prompt, info, *outputs], **quiet)
    return app


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--model', default='qwen2.5:7b', help='Ollama model tag that supports tool calling')
    parser.add_argument('--base-url', default='http://127.0.0.1:11434/v1')
    parser.add_argument('--laya-cache', help='folder for the laya-cybersec download; omit to run without it')
    parser.add_argument('--laya-device', default='cpu', choices=['cpu', 'cuda'])
    parser.add_argument('--memory-store', default=str(Path(__file__).resolve().parents[1] / 'memory' / 'permissions.sqlite'),
                        help="SQLite file for exact permissions (the repository's PermissionStore); not used by the "
                             "page, which uses Atharva's learner")
    parser.add_argument('--dataset-data', help="folder for the team dataset's files; shows the dataset row picker "
                                                "(the dataset is gated: log in to Hugging Face or set HF_TOKEN)")
    parser.add_argument('--share', action='store_true', help='public gradio.live link (needed on Colab)')
    parser.add_argument('--port', type=int, default=7860)
    args = parser.parse_args(argv)
    scanner = memory = learner = None
    if args.laya_cache:
        from .cybersec import Scanner, download
        from .learner import Learner
        scanner = Scanner(download(args.laya_cache), device=args.laya_device)
        print(f'laya-cybersec loaded in {scanner.load_seconds:.1f} s on {args.laya_device}', flush=True)
        learner = Learner()   # the page's permission memory: Atharva's learner
        print(f"Permission memory: Atharva's learner ({learner.k} approvals of a kind)", flush=True)

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
                           base_url=args.base_url, compare_judge=compare, row=row, learner=learner)

    build_app(make_session, laya_available=scanner is not None, memory=memory, rows=rows, learner=learner).queue().launch(
        share=args.share, server_name='0.0.0.0' if args.share else '127.0.0.1', server_port=args.port, theme=THEME, css=CSS)


if __name__ == '__main__':
    main()
