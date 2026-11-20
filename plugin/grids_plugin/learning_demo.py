"""Learning demo: approve 3 different asks of one kind, and the next new ask of that kind is approved for you.

The learner is the team's `CountingMemory` (grids.core.permissions.memory), unchanged, keyed by the team's
`pattern_key(..., granularity='class')`: the same tool on the same kinds of people, under the same Wall rules
(`rules_version`). For the verified ASK cases that is one group per action type: email searches, calendar lookups and
private-file reads.

- laya-cybersec reads each case's exact model state (rotated method); the Wall verdict is the one recorded in the case.
- Only laya-cybersec's own asks (NEEDS_CLARIFICATION, UNCERTAIN) are learned or answered by memory, as in the team's
  `MemoryApprovalProvider`. Anything else always reaches the person.
- After `approvals_to_allow` approvals of a group with no rejection, the group's next ask is approved without asking.
  One rejection makes memory stop that group without asking (the team's rule: memory only tightens on rejection).
- Memory learns only from the person's answers, never from its own automatic approvals.
- The cases are verified recordings: no tool actually runs.
"""
import json
from html import escape

from .look import _meter
from .session import VERIFIED_CASES, borderline

GROUPS = {'search_emails': ('📧', 'Email searches', 'an email search'),
          'search_calendar_events': ('📅', 'Calendar lookups', 'a calendar lookup'),
          'get_file_by_id': ('📁', 'Private file reads', 'a private file read')}
APPROVALS_TO_ALLOW = 3


def group_cases(cases=None):
    """Case ids per group, in file order. Borderline cases (the model allows them) and single cases are left out."""
    cases = VERIFIED_CASES if cases is None else cases
    groups = {tool: [] for tool in GROUPS}
    for case_id, case in cases.items():
        tool = case['proposed_tool_call']['tool']
        if tool in groups and not borderline(case_id):
            groups[tool].append(case_id)
    return groups


def topic(case):
    """The short subject of a case, e.g. 'budget review' (its query) or its file id."""
    arguments = case['proposed_tool_call']['arguments']
    return str(arguments.get('query') or arguments.get('file_id') or case['id'])


def rules_version(case):
    """The case's policy version without its context part: 'ptl:<Wall rules>.<context>:<rest>' -> 'ptl:<Wall rules>:<rest>'.
    The Wall's version is its rules fingerprint plus a context fingerprint (grids.wall.wall.Wall.version), and each
    recorded case has its own context, so the full version would make every request a group of its own. Different
    requests learn together only under the same Wall rules; the Wall still checks each request with its full context."""
    prefix, wall, rest = case['scope']['policy_version'].split(':', 2)
    return f"{prefix}:{wall.split('.')[0]}:{rest}"


def case_choice(case_id):
    case = VERIFIED_CASES[case_id]
    return f"{topic(case)} · {case['user_prompt'][:60]} · {case_id}"


class LearningDemo:
    """One viewer's learning session: the team's CountingMemory, the cases run so far and the ask waiting, if any."""

    def __init__(self, scanner, approvals_to_allow=APPROVALS_TO_ALLOW):
        from grids.core.permissions.memory import CountingMemory
        self.scanner, self.k = scanner, approvals_to_allow
        self.memory = CountingMemory(approvals_to_allow)
        self.groups = group_cases()
        self.history, self.pending = [], None

    @staticmethod
    def key(case):
        from grids.core.permissions.memory import pattern_key
        call = case['proposed_tool_call']
        return pattern_key(call['tool'], call['arguments'], lambda target: 'unknown', 'class', rules_version(case))

    def next_case(self, tool):
        done = {entry['id'] for entry in self.history}
        return next((case_id for case_id in self.groups[tool] if case_id not in done), None)

    def run(self, case_id):
        """laya-cybersec on the case, then memory or the person. Returns the history entry."""
        from grids.core.permissions.memory import ELIGIBLE_REASONS
        from .guard import REASONS
        if self.pending:
            raise ValueError('Answer the action that is waiting first')
        case = VERIFIED_CASES[case_id]
        entry = {'id': case_id, 'tool': case['proposed_tool_call']['tool'], 'topic': topic(case), 'prompt': case['user_prompt'],
                 'arguments': case['proposed_tool_call']['arguments'], 'key': self.key(case), 'probabilities': None,
                 'decision': None, 'reason': None, 'by': None, 'approved': None, 'learned_from': []}
        wall = case['gatekeeper_input']['wall']
        if wall['verdict'] != 'PASS':
            entry.update(decision='BLOCK', reason=wall['reason_codes'][0], by='wall', approved=False)
        else:
            result = self.scanner.decide(case['model_state'], profile='recorded_full')
            entry['probabilities'] = result['probabilities']
            decision, reason = (('ASK', 'MODEL_UNAVAILABLE') if result['error'] else ('ASK', 'UNCERTAIN') if result['tie']
                                else (result['decision'], REASONS[result['decision']]))
            entry.update(decision=decision, reason=reason)
            if decision != 'ASK':
                entry.update(by='laya', approved=decision == 'ALLOW')
            elif reason not in ELIGIBLE_REASONS:
                entry.update(by='you', learnable=False)
                self.pending = entry
            else:
                choice = self.memory.decide(entry['key'])
                if choice == 'ask':
                    entry.update(by='you', learnable=True)
                    self.pending = entry
                else:
                    approved = choice == 'allow'
                    entry.update(by='memory', approved=approved,
                                 learned_from=[e['topic'] for e in self.history
                                               if e['key'] == entry['key'] and e['by'] == 'you' and e['approved'] is approved])
        self.history.append(entry)
        return entry

    def answer(self, approved):
        """The person's answer to the waiting ask; memory learns it if it is one of laya-cybersec's own asks."""
        entry, self.pending = self.pending, None
        if entry is None:
            raise ValueError('Nothing is waiting for your answer')
        entry['approved'] = bool(approved)
        if entry.get('learnable'):
            self.memory.update(entry['key'], entry['approved'])
        return entry

    def status(self, tool):
        """(approvals, rejections, state) of a group: 'learning', 'learned' or 'stopped'."""
        approvals = rejections = 0
        for entry in self.history:
            if entry['tool'] == tool and entry['by'] == 'you' and entry.get('learnable') and entry['approved'] is not None:
                approvals, rejections = (0, rejections + 1) if not entry['approved'] else (approvals + 1, rejections)
        state = 'stopped' if rejections else 'learned' if approvals >= self.k else 'learning'
        return approvals, rejections, state


INTRO = f"""### 🧠 Permissions that learn
Approve **{APPROVALS_TO_ALLOW} different** requests of one kind, and the next **new** request of that kind is approved
for you, without asking. Each kind learns on its own, and one **Reject** stops that kind for good (until you reset).

**Try it:** pick *Email searches*, press **Run the next one** and approve it. Do that twice more, then run a fourth:
it is approved by what the guard learned from you. The cases are the team's verified ASK cases; no tool actually runs.
"""


def progress_html(demo):
    cards = []
    for tool, (icon, name, one) in GROUPS.items():
        approvals, rejections, state = demo.status(tool) if demo else (0, 0, 'learning')
        k = demo.k if demo else APPROVALS_TO_ALLOW
        dots = ''.join(f'<i class="{"on" if i < min(approvals, k) else ""}"></i>' for i in range(k))
        approved = [e['topic'] for e in (demo.history if demo else []) if e['tool'] == tool and e['by'] == 'you'
                    and e.get('learnable') and e['approved']]
        if state == 'stopped':
            say = f'✕ Stopped: you rejected {one}, so new ones are stopped without asking.'
        elif state == 'learned':
            say = f'✓ Learned: new {name.lower()} are approved for you.'
        else:
            say = f'Asks you · {approvals} of {k} approvals'
        seen = (f'<div class="seen">You approved: {escape(", ".join(approved))}</div>') if approved else ''
        cards.append(f'<div class="group {state}"><div class="gtop"><span class="gicon">{icon}</span><b>{name}</b>'
                     f'<span class="dots">{dots}</span></div><div class="gsay">{say}</div>{seen}</div>')
    return f'<div class="groups">{"".join(cards)}</div>'


def result_html(demo):
    entry = demo.history[-1] if demo and demo.history else None
    if entry is None:
        return ('<div class="card placeholder"><b>Pick a kind of request and press Run</b>The guard asks you first. '
                f'After {APPROVALS_TO_ALLOW} approvals of one kind, watch it approve the next one on its own.</div>')
    one = GROUPS[entry['tool']][2]
    if demo.pending is entry:
        kind, badge = 'ask', '? Waiting for you'
        say = ('<b>laya-cybersec is not sure your request allows this.</b> Approve or Reject below. ' +
               (f'The guard learns from your answer ({demo.status(entry["tool"])[0]} of {demo.k} approvals of this kind '
                'so far).' if entry.get('learnable') else 'This ask is a mandatory one, so it is not learned.'))
    elif entry['by'] == 'memory' and entry['approved']:
        kind, badge = 'learned', '⚡ Approved by learning'
        say = (f'<b>Not asked.</b> You approved {len(entry["learned_from"])} different '
               f'{GROUPS[entry["tool"]][1].lower()} before ({escape(", ".join(entry["learned_from"]))}), '
               'so this new one was approved for you.')
    elif entry['by'] == 'memory':
        kind, badge = 'block', '✕ Stopped by learning'
        say = f'<b>Not asked.</b> You rejected {one} before, so the guard stops this kind without asking.'
    elif entry['by'] == 'you':
        kind, badge = ('allow', '✓ Approved by you') if entry['approved'] else ('block', '✕ Rejected by you')
        say = ('<b>The guard learned from this.</b>' if entry.get('learnable') else '<b>Answered.</b> (not learned)')
    elif entry['by'] == 'laya':
        kind, badge = ('allow', '✓ Allowed') if entry['approved'] else ('block', '✕ Stopped')
        say = f'<b>laya-cybersec decided {entry["decision"]} on its own</b>, so nothing was asked or learned.'
    else:
        kind, badge, say = 'block', '✕ Stopped', '<b>Stopped by the Wall.</b> Nothing was asked or learned.'
    action = f"{escape(entry['tool'])}({escape(json.dumps(entry['arguments'], ensure_ascii=False))})"
    return (f'<div class="card"><div class="verdict"><span class="badge {kind}">{badge}</span><div class="say">{say}</div>'
            f'</div><div class="quote">“{escape(entry["prompt"])}”</div><div class="action">{action}</div>'
            + (_meter(entry['probabilities']) if entry['probabilities'] else '') + '</div>')


def history_rows(demo):
    names = {'you': 'you', 'memory': '⚡ learning (not asked)', 'laya': 'laya-cybersec', 'wall': 'the Wall'}
    rows = []
    for n, e in enumerate(demo.history if demo else [], 1):
        outcome = 'waiting' if e is demo.pending else 'approved' if e['approved'] else 'stopped'
        rows.append([n, GROUPS[e['tool']][1], e['topic'], e['decision'], names[e['by']], outcome, e['id']])
    return rows


HISTORY_HEADERS = ['#', 'Kind', 'Subject', 'laya-cybersec', 'Decided by', 'Result', 'Case']


def main(argv=None):
    """Real laya-cybersec: for each kind, APPROVALS_TO_ALLOW different requests approved, then a new one approved by
    learning."""
    import argparse
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument('--laya-cache', required=True, help='folder for the laya-cybersec download')
    parser.add_argument('--laya-device', default='cpu', choices=['cpu', 'cuda'])
    args = parser.parse_args(argv)
    from .cybersec import Scanner, download
    demo = LearningDemo(Scanner(download(args.laya_cache), device=args.laya_device))
    passed = True
    print('| Kind | Requests (who decided) | Passed |\n|---|---|---|')
    for tool, (_, name, _) in GROUPS.items():
        steps = []
        while len(steps) < demo.k + 1:
            case_id = demo.next_case(tool)
            if case_id is None:
                break
            entry = demo.run(case_id)
            if demo.pending:
                demo.answer(True)
            if entry['decision'] == 'ASK':   # a model ALLOW is not part of the learning sequence
                steps.append(entry)
            else:
                print(f'  ({case_id}: laya-cybersec answered {entry["decision"]}, skipped)')
        ok = (len(steps) == demo.k + 1 and [s['by'] for s in steps] == ['you'] * demo.k + ['memory']
              and steps[-1]['approved'])
        passed &= ok
        print(f"| {name} | " + ', '.join(f"{s['topic']} ({s['by']})" for s in steps) + f" | {'yes' if ok else '**no**'} |")
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
