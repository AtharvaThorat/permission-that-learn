"""Offline action-decision evaluation: no actor and no tool execution."""
from dataclasses import asdict
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from blackbox.contracts import BoundAction, WallVerdict
from blackbox.permissions.rules import RulesGate
from .artifacts import atomic, lines, checksum, Writer
from .aggregate import csv_file


def replay(source, config, *, allow_models=False):
    source = Path(source)
    backend = config.get('backend', 'rules_only')
    if backend not in ('rules_only', 'existing_laya'):
        raise ValueError('Unknown replay backend')
    if backend == 'existing_laya' and not allow_models:
        raise ValueError('Model replay requires explicit --allow-models')
    if backend == 'existing_laya':
        from blackbox.permissions.gatekeeper_adapter import ExistingLayaGate
        from blackbox.config import GateConfig
        from agentdojo.task_suite.load_suites import get_suite
        from agentdojo.functions_runtime import FunctionsRuntime
        gate = ExistingLayaGate(GateConfig.model_validate(config['gatekeeper']), config.get('max_chars', 24000))
        gate.set_native_schemas(FunctionsRuntime(get_suite('v1.2.2','workspace').tools))
    else:
        gate = RulesGate()
    out = source / 'replays' / uuid4().hex
    out.mkdir(parents=True, exist_ok=False)
    writer, records, sources = Writer(out), [], {}
    try:
        for path in sorted(source.glob('episodes/*/*/decisions.jsonl')):
            source_manifest = json.loads((path.parent/'manifest.json').read_text())
            source_episode = source_manifest['job']['episode_spec_id']
            sources[path.relative_to(source).as_posix()] = checksum(path)
            actions, walls = {}, {}
            for event in lines(path):
                if event['event'] == 'bound_action':
                    actions[event['action']['action_id']] = event
                elif event['event'] == 'wall':
                    walls[event['action_id']] = event['verdict']
            for action_id, entry in actions.items():
                data = dict(entry['action'])
                data['effects'] = tuple(data['effects'])
                action = BoundAction(**data)
                wall_data = walls.get(action_id)
                if wall_data is None or wall_data['verdict'] != 'PASS':
                    records.append({'source_episode':source_episode,'source_attempt':path.parent.name,
                        'action_id':action_id,'status':'not_gate_eligible','decision':None})
                    continue
                wall_data['missing'] = tuple(wall_data.get('missing', []))
                wall = WallVerdict(**wall_data)
                episode = SimpleNamespace(task=entry['task'], episode_id=path.parent.name)
                decision = gate.evaluate(episode, action, wall)
                record = {'source_episode':source_episode,'source_attempt':path.parent.name,
                    'action_id':action_id,'decision_id':uuid4().hex,'status':'evaluated',**asdict(decision)}
                writer('replay_decision', {'input':entry, 'wall':wall_data, **record})
                records.append(record)
    finally:
        gate.close()
        writer.close()
    atomic(out/'manifest.json', {'schema_version':1,'kind':'offline action-decision evaluation',
        'source_run':'../..','config':config,'source_checksums':sources,
        'limitations':'No counterfactual task utility. Source defense modes change action distributions.',
        'records':len(records)})
    csv_file(out/'decisions.csv', [{k:v for k,v in r.items() if k!='probabilities'} for r in records])
    atomic(out/'summary.json', {'records':len(records),'decisions':{d:sum(r.get('decision')==d for r in records) for d in ('ALLOW','ASK','BLOCK')}})
    return str(out)
