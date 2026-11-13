"""Team dataset rows for the chat demo: pick a Workspace row and replay it, with you answering laya-cybersec's asks.

Each row of `siddharth-magesh/grids-laya-permission-v1` is rebuilt as in `replay.py`: its simulated Workspace with the
injected text and the earlier tool calls already run, and the action the row proposes. In the demo, "Run the row's
action" sends that recorded action through the plugin; Send gives your own message to the chat model in the same Workspace.
"""
import json
from pathlib import Path

from .evaluate import download, load, reviewed_labels
from .replay import Neuralchemy, kind_of, parse, rebuild

SUITE = 'workspace'   # the chat demo shows the Workspace only


class DatasetRows:
    """The dataset's Workspace rows (downloaded once to `data_dir`; needs the gated dataset's HF token)."""

    def __init__(self, data_dir=None, rows=None):
        """`rows`: dataset rows ({'id', 'source_id', 'source_label'}) instead of downloading them (tests)."""
        from grids.gatekeeper import training_data as td
        from .evaluate import METADATA_FILE, PAIRS_FILE
        if rows is None:
            data = Path(data_dir)
            pairs, metadata = data / PAIRS_FILE, data / METADATA_FILE
            if not (pairs.is_file() and metadata.is_file()):
                pairs, metadata = download(data)
            rows, _ = load(pairs, metadata)
        published = td.Layout().published
        references = {r['source_id']: r for split in ('train', 'test') for r in td.read_jsonl(published / f'{split}.jsonl')}
        labels = reviewed_labels()
        self.rows = {}
        for row in sorted(rows, key=lambda r: r['id']):
            spec = parse(row['source_id'])
            if spec['suite'] == SUITE:
                self.rows[row['id']] = {'row': row, 'spec': spec, 'reference': references[row['source_id']],
                                        'reviewed_label': (labels.get(row['id']) or {}).get('reviewed_label')}
        self.suite, self.neuralchemy = None, Neuralchemy()

    def choices(self):
        """(label, row id) pairs for the picker."""
        return [(f"{i} · {json.loads(r['reference']['context'])['untrusted_proposed_action']['tool']} · "
                 f"{kind_of(r['spec'])} · reviewed {r['reviewed_label'] or '-'}", i) for i, r in self.rows.items()]

    def load(self, row_id):
        """The row rebuilt: its Workspace, earlier history and proposed call."""
        from grids.gatekeeper import training_data as td
        item = self.rows[row_id]
        if self.suite is None:
            self.suite = td.Suite(SUITE)
        with td.frozen_clock():   # the dataset was built with a pinned clock
            env, messages, call, mapping, exact = rebuild(self.suite, item['spec'], item['reference'], self.neuralchemy)
        return {'id': row_id, 'suite': self.suite, 'spec': item['spec'], 'prompt': item['reference']['prompt'],
                'env': env, 'messages': messages, 'call': call, 'mapping': mapping, 'exact': exact,
                'kind': kind_of(item['spec']), 'reviewed_label': item['reviewed_label'],
                'source_label': item['row'].get('source_label')}


def earlier_steps(messages, limit=400):
    """The row's earlier tool calls and results as chat messages (already run when the row is loaded)."""
    chat, names = [], {}
    for m in messages:
        if m['role'] == 'user':
            chat.append({'role': 'user', 'content': m['content'] if isinstance(m['content'], str) else str(m['content'])})
        elif m['role'] == 'assistant':
            for c in m.get('tool_calls') or []:
                names[c['id']] = c['function']['name']
                chat.append({'role': 'assistant', 'content': f"(earlier step) calls `{c['function']['name']}` "
                                                             f"{c['function']['arguments'][:limit]}"})
        elif m['role'] == 'tool':
            text = m['content'] if isinstance(m['content'], str) else str(m['content'])
            more = ' …' if len(text) > limit else ''
            chat.append({'role': 'assistant', 'content': f"(earlier step) `{names.get(m['tool_call_id'], 'tool')}` "
                                                         f"returned:\n\n```\n{text[:limit]}{more}\n```"})
    return chat
