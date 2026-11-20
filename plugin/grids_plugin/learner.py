"""Atharva's learner as the demo page's permission memory.

The team's `CountingMemory` and `pattern_key(..., granularity='class')` (grids.core.permissions.memory, Atharva), unchanged:

- A kind of request = the same tool, reaching the same kinds of people (trust classes from the Wall's own context),
  under the same Wall rules.
- "Approve and remember" teaches an approval; Reject teaches a rejection; a plain Approve allows this once and teaches
  nothing.
- After `APPROVALS_TO_ALLOW` remembered approvals of a kind with no rejection, the next ask of that kind is approved
  without asking, even for a different request. One rejection makes it stop that kind without asking (the team's rule:
  memory only tightens on rejection) until "Forget what it learned".
- Only laya-cybersec's own asks with complete evidence are answered or learned (`ELIGIBLE_REASONS`, as before);
  mandatory confirmations, incomplete evidence and model failures always reach the person.
"""
import json
import threading

APPROVALS_TO_ALLOW = 3
LABEL = f"Atharva's learner ({APPROVALS_TO_ALLOW} approvals of a kind)"
APPROVED, STOPPED = 'approved by the learner', 'stopped by the learner'   # row notes: nobody is asked


def rules_version(policy_version):
    """'ptl:<Wall rules>.<context>:<rest>' -> 'ptl:<Wall rules>:<rest>'. The Wall's version is its rules fingerprint plus
    a context fingerprint (grids.wall.wall.Wall.version), and each verified case has its own context, so the full version
    would make every request a kind of its own. The Wall still checks each request with its full context."""
    parts = str(policy_version).split(':', 2)
    if len(parts) != 3 or '.' not in parts[1]:
        return str(policy_version)
    return f"{parts[0]}:{parts[1].split('.')[0]}:{parts[2]}"


class Learner:
    """One learner shared by every session on the page (what it learned outlives a Workspace reset)."""

    def __init__(self, approvals_to_allow=APPROVALS_TO_ALLOW):
        from grids.core.permissions.memory import CountingMemory
        self.k, self.lock = approvals_to_allow, threading.Lock()
        self.memory, self.taught = CountingMemory(approvals_to_allow), []

    @staticmethod
    def key(tool, arguments, policy_version, classify):
        from grids.core.permissions.memory import pattern_key
        return pattern_key(tool, arguments, classify, 'class', rules_version(policy_version))

    def decide(self, key):
        """'allow', 'block' or 'ask' for one eligible ask."""
        with self.lock:
            return self.memory.decide(key)

    def teach(self, key, approved, tool, request):
        with self.lock:
            self.memory.update(key, bool(approved))
            self.taught.append({'key': key, 'tool': tool, 'request': request, 'approved': bool(approved)})

    def progress(self, key):
        """(approvals, rejections) of one kind so far."""
        with self.lock:
            record = self.memory.records.get(key)
        return (record.approvals, record.rejections) if record else (0, 0)

    def forget(self):
        from grids.core.permissions.memory import CountingMemory
        with self.lock:
            self.memory, self.taught = CountingMemory(self.k), []

    def kinds(self):
        """What it learned, one entry per kind: tool, who it reaches, approvals, rejections, state and requests."""
        out = {}
        with self.lock:
            records = dict(self.memory.records)
            taught = list(self.taught)
        for item in taught:
            entry = out.setdefault(item['key'], {'tool': item['tool'], 'requests': []})
            if item['request'] not in entry['requests']:
                entry['requests'].append(item['request'])
        for key, entry in out.items():
            record = records.get(key)
            approvals, rejections = (record.approvals, record.rejections) if record else (0, 0)
            reaches = [c for c in json.loads(key)[2] if c != 'none']
            entry.update(reaches=', '.join(reaches) or 'no other people', approvals=approvals, rejections=rejections,
                         state='stopped' if rejections else 'learned' if approvals >= self.k else 'learning')
        return list(out.values())

    def provider(self, inner, classify, record=None):
        return LearnerApprovalProvider(inner, self, classify, record)


class LearnerApprovalProvider:
    """Answers an eligible ask from the learner, else asks `inner` (the person on the page). It does not learn here: the
    page teaches it only on "Approve and remember" or Reject (DemoSession.respond)."""

    def __init__(self, inner, learner, classify, record=None):
        self.inner, self.learner, self.classify, self.record = inner, learner, classify, record

    def request(self, pending):
        from grids.core.permissions.approvals import ApprovalEvent
        from grids.core.permissions.memory import ELIGIBLE_REASONS
        metadata = json.loads(pending.decision_metadata)
        if (pending.reason not in ELIGIBLE_REASONS or metadata.get('error_kind')
                or not pending.action.evidence_complete):
            return self.inner.request(pending)
        key = self.learner.key(pending.action.tool, json.loads(pending.action.arguments_json),
                               pending.action.policy_version, self.classify)
        choice = self.learner.decide(key)
        if self.record:
            self.record({'binding': {'action_id': pending.binding.action_id}, 'key': key, 'learner': choice,
                         'action': 'USE_EXISTING_GRANT' if choice == 'allow' else 'ASK_USER',
                         'recommendation': 'USE_EXISTING_GRANT' if choice == 'allow' else 'ASK_USER'})
        if choice in ('allow', 'block'):
            return ApprovalEvent(pending.pending_id, pending.binding, choice == 'allow')
        return self.inner.request(pending)
