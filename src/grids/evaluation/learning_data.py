"""Recorded Laya predictions for arbitrary `laya_input` rows (synthetic users, fine-tuned checkpoints).

Predictions are keyed by a hash of the exact input, so repeated inputs are scored once and any row can be
joined back without trusting ids. The method and the fail-closed validation are those of `permission_sim`.
"""
import hashlib
import json
from pathlib import Path
from .memory_sim import read_jsonl, sha256
from .permission_sim import DECISIONS, asked_questions, laya_agent, package_versions, predict_state


def input_key(laya_input):
    return hashlib.sha256(laya_input.encode('utf-8')).hexdigest()[:24]


def predict_inputs(input_paths, metadata_path, output, model_dir=None, profile='cybersec', method='rotated',
                   device='cpu', limit=None):
    """Score every distinct `laya_input` of the given JSONL files with the pinned or a local checkpoint."""
    metadata = json.loads(Path(metadata_path).read_text(encoding='utf-8'))
    pin, question = metadata['question_and_checkpoint_provenance'][profile], metadata['laya_question']
    asked = asked_questions(question, method)
    states = {}
    for path in input_paths:
        for row in read_jsonl(path):
            states.setdefault(input_key(row['laya_input']), row['laya_input'])
    keys = sorted(states)[:limit]
    agent = laya_agent(pin, model_dir, device)
    header = {'checkpoint': str(model_dir) if model_dir else pin['checkpoint'],
              'revision': None if model_dir else pin['revision'], 'base': pin, 'device': device,
              'inputs': {Path(p).name: sha256(p) for p in input_paths}, 'metadata_sha256': sha256(metadata_path),
              'question_sha256': hashlib.sha256(json.dumps(question, sort_keys=True).encode()).hexdigest(),
              'method': method, 'questions_asked': list(asked), 'rows': len(keys), 'packages': package_versions()}
    lines = [json.dumps({'header': header}, sort_keys=True)]
    for key in keys:
        record = predict_state(agent, states[key], asked, method)
        answers = record.pop('answers', None)
        # Per-order choices are kept (rotation agreement); per-order probabilities are not, to keep files small.
        record['orders'] = [answers[q]['choice'] for q in asked] if answers else None
        lines.append(json.dumps({'key': key, **record}, sort_keys=True))
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return header


def load_input_predictions(path):
    lines = read_jsonl(path)
    return lines[0]['header'], {r['key']: r for r in lines[1:]}


def gate_of(row, predictions):
    """A row's recorded gatekeeper output: decision (or ERROR), mean probabilities, rotation agreement."""
    record = predictions.get(input_key(row['laya_input']))
    if record is None:
        raise ValueError(f"{row['id']}: no recorded Laya prediction")
    if record['error'] or record['decision'] not in DECISIONS:
        return {'decision': 'ERROR', 'probabilities': None, 'unanimous': False}
    orders = record.get('orders') or []
    return {'decision': record['decision'], 'probabilities': record['probabilities'],
            'unanimous': len(set(orders)) == 1 and bool(orders)}
