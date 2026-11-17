"""The chat demo's look: theme, styles, the header and the live pipeline view of the latest action.

Decision colors are the status palette (good / warning / critical) and always come with an icon and a label, so color
never carries a decision alone. Everything shown from a session is escaped.
"""
from html import escape
import json

import gradio as gr

THEME = gr.themes.Soft(
    primary_hue='blue', secondary_hue='slate', neutral_hue='slate', radius_size='lg',
    font=[gr.themes.GoogleFont('Inter'), 'ui-sans-serif', 'system-ui', 'sans-serif'],
    font_mono=[gr.themes.GoogleFont('JetBrains Mono'), 'ui-monospace', 'Consolas', 'monospace'])

# Status palette: good, warning, critical. Ink on the warning fill is dark; on the others white.
DECISIONS = {'ALLOW': ('allow', '✓', 'Allow'), 'ASK': ('ask', '?', 'Ask you'), 'BLOCK': ('block', '✕', 'Block')}

CSS = """
.gradio-container { width: 100% !important; max-width: 1320px !important; margin: 0 auto !important; }
:root, .gradio-container {
  --ok: #0ca30c; --warn: #fab219; --bad: #d03b3b;
  --ok-tint: rgba(12,163,12,.10); --warn-tint: rgba(250,178,25,.16); --bad-tint: rgba(208,59,59,.10);
  --line: rgba(11,11,11,.10); --soft: rgba(42,120,214,.07);
}
.dark .gradio-container { --line: rgba(255,255,255,.12); --soft: rgba(57,135,229,.12); }

/* Header */
.hero { padding: 26px 30px; border-radius: 18px; color: #fff; margin-bottom: 6px;
  background: radial-gradient(1200px 260px at 0% 0%, #2a78d6 0%, #1d4e94 45%, #10284f 100%); }
.hero, .hero * { color: #fff !important; }
.hero h1 { margin: 0 0 6px; font-size: 30px; line-height: 1.15; letter-spacing: -0.02em; }
.hero p.lead { margin: 0 0 18px; font-size: 16px; opacity: .92; max-width: 760px; }
.hero .layers { display: flex; gap: 10px; flex-wrap: wrap; }
.hero .layer { flex: 1 1 220px; background: rgba(255,255,255,.10); border: 1px solid rgba(255,255,255,.18);
  border-radius: 12px; padding: 12px 14px; }
.hero .layer b { display: block; font-size: 14px; margin-bottom: 2px; }
.hero .layer span { font-size: 13px; opacity: .85; }
.hero .stats { margin-top: 14px; font-size: 13px; opacity: .85; }

/* Panels and step titles */
.panel { border: 1px solid var(--line) !important; border-radius: 16px !important; padding: 16px !important; }
.step-title h3 { margin: 0 !important; font-size: 15px !important; letter-spacing: .01em; }
.step-title h3 span { display: inline-flex; width: 22px; height: 22px; border-radius: 50%; align-items: center;
  justify-content: center; background: #2a78d6; color: #fff; font-size: 12px; margin-right: 8px; }
.pills .wrap { gap: 6px !important; }
.pills label { border-radius: 999px !important; padding: 6px 12px !important; }
.quick button { font-weight: 600 !important; }

/* Pipeline strip */
.pipe { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 8px; margin-bottom: 14px; }
.stepcard { position: relative; border: 1px solid var(--line); border-radius: 14px; padding: 12px 12px 11px;
  background: var(--block-background-fill); min-height: 104px; transition: all .3s ease; }
.stepcard .top { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.stepcard .dot { width: 26px; height: 26px; border-radius: 50%; display: inline-flex; align-items: center;
  justify-content: center; font-weight: 700; font-size: 14px; background: var(--line); color: var(--body-text-color); }
.stepcard .name { font-weight: 650; font-size: 13.5px; }
.stepcard .detail { font-size: 12.5px; color: var(--body-text-color-subdued); line-height: 1.35; overflow-wrap: anywhere; }
.stepcard.pass { border-color: var(--ok); background: var(--ok-tint); }
.stepcard.pass .dot { background: var(--ok); color: #fff; }
.stepcard.stop { border-color: var(--bad); background: var(--bad-tint); }
.stepcard.stop .dot { background: var(--bad); color: #fff; }
.stepcard.wait { border-color: var(--warn); background: var(--warn-tint); animation: glow 1.6s ease-in-out infinite; }
.stepcard.wait .dot { background: var(--warn); color: #0b0b0b; }
.stepcard.active { border-color: #2a78d6; background: var(--soft); }
.stepcard.active .dot { background: #2a78d6; color: #fff; animation: spin 1.1s linear infinite; }
.stepcard.skip { opacity: .55; border-style: dashed; }
@keyframes glow { 0%,100% { box-shadow: 0 0 0 0 rgba(250,178,25,.0); } 50% { box-shadow: 0 0 0 6px rgba(250,178,25,.28); } }
@keyframes spin { to { transform: rotate(360deg); } }

/* Decision card */
.card { border: 1px solid var(--line); border-radius: 16px; padding: 18px 20px; background: var(--block-background-fill); }
.verdict { display: flex; align-items: center; gap: 14px; margin-bottom: 14px; }
.badge { display: inline-flex; align-items: center; gap: 8px; border-radius: 999px; padding: 8px 16px; font-weight: 700;
  font-size: 15px; white-space: nowrap; }
.badge.allow { background: var(--ok); color: #fff; } .badge.block { background: var(--bad); color: #fff; }
.badge.ask { background: var(--warn); color: #0b0b0b; } .badge.idle { background: var(--line); color: var(--body-text-color); }
.verdict .say { font-size: 14.5px; line-height: 1.4; }
.verdict .say b { font-size: 16px; }
.quote { border-left: 3px solid #2a78d6; padding: 6px 12px; margin: 0 0 10px; font-size: 14.5px; border-radius: 4px;
  background: var(--soft); }
.action { font-family: var(--font-mono); font-size: 12.5px; padding: 8px 12px; border-radius: 10px;
  background: var(--background-fill-secondary); overflow-wrap: anywhere; margin-bottom: 14px; }
.meter-title { font-size: 12.5px; color: var(--body-text-color-subdued); margin-bottom: 6px; }
.meter { display: flex; gap: 2px; height: 14px; border-radius: 7px; overflow: hidden; background: var(--line); }
.meter > div { height: 100%; transition: width .6s ease; }
.meter .allow { background: var(--ok); } .meter .ask { background: var(--warn); } .meter .block { background: var(--bad); }
.legend { display: flex; gap: 16px; flex-wrap: wrap; margin-top: 7px; font-size: 13px; }
.legend span i { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 6px; }
.legend .lead { font-weight: 700; }
.placeholder { text-align: center; padding: 34px 10px; color: var(--body-text-color-subdued); font-size: 15px; }
.placeholder b { display: block; font-size: 18px; color: var(--body-text-color); margin-bottom: 4px; }

/* Approval panel: neutral until the guard asks, then it glows (its buttons are enabled only while something waits) */
.approval { border: 1px solid var(--line) !important; border-radius: 16px !important; padding: 12px 16px !important;
  margin-top: 12px !important; transition: all .3s ease; }
.approval:has(.approve-btn:not(:disabled)) { border: 2px solid var(--warn) !important; background: var(--warn-tint) !important;
  animation: glow 1.6s ease-in-out infinite; }
.approval h4 { margin: 0 0 4px !important; }
.approve-btn { background: var(--ok) !important; color: #fff !important; border: none !important; }
.remember-btn { background: #1d4e94 !important; color: #fff !important; border: none !important; }
.reject-btn { background: var(--bad) !important; color: #fff !important; border: none !important; }
.approve-btn:disabled, .remember-btn:disabled, .reject-btn:disabled { opacity: .35 !important; }

.quick { flex-wrap: wrap !important; }
.quick > * { min-width: 180px !important; }
@media (max-width: 900px) {
  .pipe { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .hero { padding: 20px; } .hero h1 { font-size: 24px; }
  .main-row { flex-direction: column !important; }
  .main-row > * { min-width: 0 !important; width: 100% !important; }
}
"""


def hero(verified_count, dataset_rows=0):
    rows = f' · {dataset_rows} team dataset rows' if dataset_rows else ''
    return f"""
<div class="hero">
  <h1>Permissions That Learn</h1>
  <p class="lead">An AI assistant wants to act on your mailbox, calendar and files. Before anything runs, a guard checks
  that <b>your request</b> really allows it, and asks you when it is not sure.</p>
  <div class="layers">
    <div class="layer"><b>🧱 The Wall</b><span>Your fixed rules: only email contacts, never share outside work, never
    delete. Plain code, no AI, under 1 ms.</span></div>
    <div class="layer"><b>🧠 laya-cybersec</b><span>A 322M-parameter model on the CPU decides Allow, Ask you or Block for
    each action the Wall lets through.</span></div>
    <div class="layer"><b>🗂️ Permission memory</b><span>“Approve and remember” saves an exact permission, so the same
    request does not ask you twice. Revoke it anytime.</span></div>
  </div>
  <div class="stats">{verified_count} verified ASK cases from the team{rows} · everything runs on AgentDojo's simulated
  Workspace, nothing real is touched</div>
</div>"""


HOW_IT_WORKS = """
### How it works
1. **The assistant proposes an action**, for example `search_emails` or `share_file`, with exact arguments.
2. **The Wall** checks your fixed rules. A broken rule stops the action at once, with no AI involved.
3. **laya-cybersec** reads your request, the action and the evidence, and answers **Allow**, **Ask you** or **Block**.
4. **You decide** when it asks: *Approve*, *Approve and remember*, or *Reject*. Nothing runs until you choose.
   With memory on, a remembered permission answers the same request next time, so you are not asked again.
5. **The executor** rechecks the exact action and runs it, or refuses.

The verified ASK cases are requests that say *“wait for my explicit confirmation”*. laya-cybersec reads each case's
exact recorded input; no tool runs, as in the team's runner. Everything acts on AgentDojo's simulated Workspace.
"""


def probabilities_of(text):
    """'ALLOW 0.10 · ASK 0.10 · BLOCK 0.80' (the decisions table's form) as a dict, or None."""
    out = {}
    for part in (text or '').split(' · '):
        label, _, value = part.partition(' ')
        try:
            out[label] = float(value)
        except ValueError:
            return None
    return out if set(out) == set(DECISIONS) else None


def _step(name, icon, state, detail):
    return (f'<div class="stepcard {state}"><div class="top"><span class="dot">{icon}</span>'
            f'<span class="name">{escape(name)}</span></div><div class="detail">{detail}</div></div>')


def _meter(probabilities):
    lead = max(probabilities, key=probabilities.get)
    bars = ''.join(f'<div class="{DECISIONS[k][0]}" style="width:{max(probabilities[k] * 100, 0.5):.1f}%" '
                   f'title="{DECISIONS[k][2]} {probabilities[k]:.0%}"></div>' for k in DECISIONS)
    legend = ''.join(f'<span class="{"lead" if k == lead else ""}"><i class="{DECISIONS[k][0]}" '
                     f'style="background:var(--{dict(allow="ok", ask="warn", block="bad")[DECISIONS[k][0]]})"></i>'
                     f'{DECISIONS[k][1]} {DECISIONS[k][2]} {probabilities[k]:.0%}</span>' for k in DECISIONS)
    return (f'<div class="meter-title">How sure laya-cybersec is</div><div class="meter">{bars}</div>'
            f'<div class="legend">{legend}</div>')


def stage_html(session):
    """The latest action as a pipeline that lights up step by step, and its decision card."""
    if session is None or (not session.rows and not session.running and session.row is None):
        return ('<div class="card placeholder"><b>Pick an action and press Run</b>The pipeline lights up here step by step: '
                'the Wall, laya-cybersec, you, and the result.</div>')
    row = list(session.rows.values())[-1] if session.rows else None
    item = session.row or {}
    verified = bool(item.get('verified'))
    request = item.get('prompt') or session.last_prompt or ''
    waiting = session.pending
    running = session.running
    result = session.row_result if verified or item.get('call') else None
    probabilities = probabilities_of(row and row.get('gate_output'))

    steps = [_step('Request', '1', 'pass', escape(request[:64] + ('…' if len(request) > 64 else '')) or '&nbsp;')]
    wall = (row or {}).get('wall') or ''
    wall_stopped = wall not in ('', 'off') and not wall.startswith('PASS')
    if not row:
        steps.append(_step('The Wall', '·', 'active', 'Checking your rules…'))
    elif wall == 'off':
        steps.append(_step('The Wall', '–', 'skip', 'Off in this pipeline'))
    elif wall_stopped:
        steps.append(_step('The Wall', '✕', 'stop', f"Stopped it: {escape(str(row.get('wall_reason') or wall))}"))
    else:
        steps.append(_step('The Wall', '✓', 'pass', 'Allowed by your rules' + (' (recorded verdict)' if 'in case' in wall else '')))

    if session.gate is None:
        steps.append(_step('laya-cybersec', '–', 'skip', 'Not in this protection level'))
    elif wall_stopped:
        steps.append(_step('laya-cybersec', '–', 'skip', 'Not needed: the Wall decided'))
    elif probabilities:
        lead = max(probabilities, key=probabilities.get)
        state = {'ALLOW': 'pass', 'ASK': 'wait', 'BLOCK': 'stop'}[lead]
        steps.append(_step('laya-cybersec', DECISIONS[lead][1], state, f'{DECISIONS[lead][2]} ({probabilities[lead]:.0%} sure)'))
    else:
        steps.append(_step('laya-cybersec', '·', 'active' if running else 'skip', 'Reading the request…' if running else '—'))

    memory = (row or {}).get('memory') or ''
    person = (result or {}).get('person')
    decision = (row or {}).get('decision')
    if memory == 'answered by remembered permission':
        steps.append(_step('You / memory', '✓', 'pass', 'Memory answered: you approved this before'))
    elif waiting:
        steps.append(_step('You / memory', '?', 'wait', 'Waiting for your decision'))
    elif person == 'approved':
        steps.append(_step('You / memory', '✓', 'pass', 'You approved' + (' and it was remembered' if 'remembered' in memory else '')))
    elif person == 'rejected':
        steps.append(_step('You / memory', '✕', 'stop', 'You rejected it'))
    elif row and decision and not running:
        steps.append(_step('You / memory', '–', 'skip', 'Not asked'))
    else:
        steps.append(_step('You / memory', '·', 'skip' if not running else 'active', '—'))

    executed = (row or {}).get('executed')
    if waiting or running or not row:
        steps.append(_step('Result', '·', 'active' if running and not waiting else 'skip', 'Waiting…' if waiting else 'Working…'))
        kind, say = (('ask', '<b>Nothing runs until you choose.</b> laya-cybersec is not sure your request allows this '
                      'action. Use the buttons below.') if waiting else ('idle', 'The guard is checking this action.'))
    elif executed:
        how = ('your remembered permission' if memory == 'answered by remembered permission' else
               'you' if person == 'approved' else 'the guard')
        steps.append(_step('Result', '✓', 'pass', 'Allowed' + (' (verified case: no tool actually runs)' if verified else ', it ran')))
        kind, say = 'allow', f'<b>Allowed by {how}.</b>'
    else:
        who = ('you' if person == 'rejected' else 'the Wall' if wall_stopped else 'laya-cybersec' if decision == 'BLOCK'
               else 'the guard')
        steps.append(_step('Result', '✕', 'stop', 'Not done'))
        kind, say = 'block', f'<b>Stopped by {who}.</b> Nothing ran.'

    tool = (row or {}).get('tool') or (item.get('call').function if item.get('call') else '')
    arguments = (row or {}).get('arguments')
    if arguments is None and item.get('call'):
        arguments = dict(item['call'].args)
    action = f'{escape(tool)}({escape(json.dumps(arguments, ensure_ascii=False)[:220]) if arguments is not None else ""})'
    card = (f'<div class="card"><div class="verdict"><span class="badge {kind}">{BADGES[kind]}</span>'
            f'<div class="say">{say}</div></div>'
            + (f'<div class="quote">“{escape(request)}”</div>' if request else '')
            + (f'<div class="action">{action}</div>' if tool else '')
            + (_meter(probabilities) if probabilities else '') + '</div>')
    return f'<div class="pipe">{"".join(steps)}</div>{card}'


BADGES = {'ask': '? Waiting for you', 'allow': '✓ Allowed', 'block': '✕ Stopped', 'idle': '… Checking'}
