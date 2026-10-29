"""Immutable action/context datasets, independently reviewed labels, no model calls."""
from pathlib import Path
from typing import Any, Literal
from pydantic import Field
from grids.core.actions import digest, parse_json
from grids.core.config import Strict, AGENTDOJO_REVISION
from grids.core.permissions.approvals import exclusive_json
from grids.runs.artifacts import checksum, lines, now


class ActionInput(Strict):
    suite: Literal['workspace', 'slack', 'banking']
    benchmark_version: Literal['v1.2.2']
    agentdojo_revision: Literal[AGENTDOJO_REVISION]
    user_request: str = Field(min_length=1)
    raw_call: Any
    messages: list[dict]
    environment: dict
    schemas: list[dict]
    wall_config: dict
    policy: dict
    trusted_identities: dict
    metadata: dict


class Record(Strict):
    schema_version: Literal[1] = 1
    record_id: str
    context_id: str
    source: dict
    capture_status: Literal['proposed', 'cancelled', 'batch_parse_failed']
    input: ActionInput


def write_dataset(records, output):
    records = [Record.model_validate(r).model_dump(mode='json') for r in records]
    if not records or len({r['record_id'] for r in records}) != len(records):
        raise ValueError('Dataset must contain unique observations')
    for r in records:
        if r['context_id'] != digest(r['input']) or r['record_id'] != digest(r['source']):
            raise ValueError('Action/context identity mismatch')
    out = Path(output)
    out.mkdir(parents=True, exist_ok=False)
    exclusive_json(out / 'actions.json', records)
    manifest = {'schema_version': 1, 'kind': 'frozen_authorization_actions', 'created_at': now(),
                'dataset_id': digest(records), 'records': len(records),
                'actions_sha256': checksum(out / 'actions.json'), 'labels': 'not supplied'}
    exclusive_json(out / 'manifest.json', manifest)
    return manifest


def load_dataset(directory):
    directory = Path(directory)
    manifest = parse_json((directory / 'manifest.json').read_text(encoding='utf-8'))
    if manifest['schema_version'] != 1 or manifest['kind'] != 'frozen_authorization_actions':
        raise ValueError('Unsupported dataset schema')
    if checksum(directory / 'actions.json') != manifest['actions_sha256']:
        raise ValueError('Dataset checksum mismatch')
    records = [Record.model_validate(r).model_dump(mode='json') for r in
               parse_json((directory / 'actions.json').read_text(encoding='utf-8'))]
    if len(records) != manifest['records'] or digest(records) != manifest['dataset_id']:
        raise ValueError('Dataset manifest mismatch')
    if len({r['record_id'] for r in records}) != len(records):
        raise ValueError('Duplicate observations')
    for r in records:
        if digest(r['input']) != r['context_id'] or digest(r['source']) != r['record_id']:
            raise ValueError('Action/context identity mismatch')
    return manifest, records


def capture(run_dirs, output):
    records = []
    for run in map(Path, run_dirs):
        for manifest_path in sorted(run.glob('episodes/*/*/manifest.json')):
            folder = manifest_path.parent
            manifest = parse_json(manifest_path.read_text(encoding='utf-8'))
            context_path = folder / 'permission-context.json'
            if not context_path.exists():
                raise ValueError('Source predates decision-time capture; recollect rather than invent context')
            context = parse_json(context_path.read_text(encoding='utf-8'))
            result_path = folder / 'result.json'
            if result_path.exists():
                result = parse_json(result_path.read_text(encoding='utf-8'))
                for relative, expected in result['checksums'].items():
                    target = (folder / relative).resolve()
                    if not target.is_relative_to(folder.resolve()) or checksum(target) != expected:
                        raise ValueError('Source attempt checksum mismatch')
            batches, snapshots = {}, {}
            for event in lines(folder / 'decisions.jsonl'):
                if event['event'] == 'proposal_batch': batches[event['turn']] = event
                if event['event'] == 'proposal_context': snapshots[event['turn'], event['offset']] = event
            job = manifest['job']
            for turn, batch in sorted(batches.items()):
                for offset, call in enumerate(batch['response'].get('tool_calls') or []):
                    snapshot = snapshots.get((turn, offset), batch)
                    source = {'run': manifest['run_id'], 'episode': job['episode_spec_id'],
                        'attempt': manifest['attempt_id'], 'turn': turn, 'offset': offset,
                        'actor': job['actor'], 'actor_profile': job['actor_profile'], 'mode': job['mode'],
                        'task': job['task'], 'attack_id': job['attack']['id'] if job['attack'] else None,
                        'seed': job['seed'], 'repetition': job['repetition'],
                        'source_trace_sha256': checksum(folder / 'decisions.jsonl')}
                    raw = dict(context, user_request=batch['task'], raw_call=call,
                               messages=snapshot['messages'], environment=snapshot['environment'], schemas=batch['schemas'])
                    records.append({'record_id': digest(source), 'context_id': digest(raw), 'source': source,
                        'input': raw, 'capture_status': ('batch_parse_failed' if snapshot is batch else
                            'proposed' if snapshot['dispatch_eligible'] else 'cancelled')})
    return write_dataset(records, output)


class Label(Strict):
    dataset_id: str
    record_id: str
    context_id: str
    decision: Literal['ALLOW', 'BLOCK', 'ASK'] | None = None
    rationale: str = ''
    evidence: list[str] = Field(default_factory=list)
    reviewer: str = ''
    status: Literal['unreviewed', 'reviewed', 'disputed'] = 'unreviewed'


def export_labels(dataset, output):
    if Path(output).resolve().is_relative_to(Path(dataset).resolve()):
        raise ValueError('Labels must be outside the immutable dataset')
    manifest, records = load_dataset(dataset)
    # Deliberately exclude all evaluated-system predictions and native scores.
    exclusive_json(output, [Label(dataset_id=manifest['dataset_id'], record_id=r['record_id'],
                                  context_id=r['context_id']).model_dump() for r in records])
    return {'template': str(output), 'records': len(records)}


def load_labels(dataset, file):
    manifest, records = load_dataset(dataset)
    known = {r['record_id']: r for r in records}
    labels = {}
    for raw in parse_json(Path(file).read_text(encoding='utf-8')):
        label = Label.model_validate(raw)
        if (label.dataset_id != manifest['dataset_id'] or label.record_id not in known or
                known[label.record_id]['context_id'] != label.context_id):
            raise ValueError('Label identity does not match frozen dataset')
        if label.record_id in labels: raise ValueError('Duplicate/conflicting label')
        if label.status == 'reviewed' and (not label.decision or not label.rationale.strip()
                or not label.reviewer.strip() or not label.evidence or not all(x.strip() for x in label.evidence)):
            raise ValueError('Reviewed labels require decision, reviewer, rationale and evidence')
        labels[label.record_id] = label.model_dump()
    return labels


def import_labels(dataset, file, output):
    if Path(output).resolve().is_relative_to(Path(dataset).resolve()):
        raise ValueError('Labels must be outside the immutable dataset')
    labels = load_labels(dataset, file)
    exclusive_json(output, list(labels.values()))
    return {'labels': str(output), 'reviewed': sum(r['status'] == 'reviewed' for r in labels.values()),
            'sha256': checksum(output)}
