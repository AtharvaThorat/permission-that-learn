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


def checkpoint_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


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
    if not keys or (limit is not None and limit < 1):
        raise ValueError('At least one input and a positive limit are required')
    local_files = {}
    if model_dir:
        root = Path(model_dir)
        local_files = {p.relative_to(root).as_posix(): checkpoint_hash(p)
                       for p in sorted(root.rglob('*')) if p.is_file()}
        if not local_files:
            raise ValueError('Local checkpoint directory is empty or missing')
    header = {'checkpoint': str(model_dir) if model_dir else pin['checkpoint'],
              'revision': None if model_dir else pin['revision'], 'base': pin, 'device': device,
              'inputs': [sha256(p) for p in input_paths], 'metadata_sha256': sha256(metadata_path),
              'local_files': local_files, 'input_keys': keys,
              'question_sha256': hashlib.sha256(json.dumps(question, sort_keys=True).encode()).hexdigest(),
              'method': method, 'questions_asked': asked, 'rows': len(keys), 'packages': package_versions()}
    out = Path(output)
    if out.exists():
        previous, records = load_input_predictions(out)
        if previous != header or set(records) != set(keys):
            raise ValueError('Output exists with different provenance or incomplete rows; use a new output path')
        return header
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps({'header': header}, sort_keys=True) + '\n')
        stream.flush()
        try:
            agent = laya_agent(pin, model_dir, device)
            initialization_error = None
        except Exception as exc:
            initialization_error = f'{type(exc).__name__}: {exc}'
        for key in keys:
            record = (predict_state(agent, states[key], asked, method) if initialization_error is None else
                      {'decision': None, 'probabilities': None, 'answers': None,
                       'error': initialization_error, 'error_kind': 'initialization_error'})
            answers = record.get('answers')
            record['orders'] = [answers[q]['choice'] for q in asked] if answers else None
            stream.write(json.dumps({'key': key, **record}, sort_keys=True) + '\n')
            stream.flush()
    return header


def load_input_predictions(path):
    lines = read_jsonl(path)
    if not lines or 'header' not in lines[0]:
        raise ValueError('Missing prediction provenance header')
    keys = [row['key'] for row in lines[1:]]
    if len(keys) != len(set(keys)):
        raise ValueError('Duplicate prediction input keys')
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
