"""Compare a fresh real single-question run with the compact development snapshot."""
import argparse
import hashlib
import json
from pathlib import Path
from scripts.experiment import ROOT


def verify(path):
    snapshot = ROOT / 'benchmarks/development'
    saved = json.loads((snapshot / 'observations.json').read_text())['single']
    summary = json.loads((path / 'summary.json').read_text(encoding='utf-8'))
    def rows(file):
        values = [json.loads(line) for line in file.read_text(encoding='utf-8').splitlines()]
        indexed = {r['case_id']: r for r in values}
        if len(indexed) != len(values):
            raise ValueError('Duplicate case IDs')
        return indexed
    old, new = rows(snapshot / 'predictions.jsonl'), rows(path / 'predictions.jsonl')
    model = summary['model']
    controls = (summary['status'] == 'completed' and summary['question_mode'] == 'single'
        and model['actual_checkpoint'] == saved['checkpoint'] and model['revision'] == saved['revision']
        and model['device'] == 'cpu' and model['config'] == saved['config']
        and summary['dependencies'] == saved['dependencies']
        and summary['fixture_sha256'] == hashlib.sha256((ROOT / 'data/gatekeeper_smoke_cases.jsonl').read_bytes()).hexdigest()
        and json.dumps(summary['question_template']) == json.dumps(json.loads((snapshot / 'single-question.json').read_text()))
        and old.keys() == new.keys())
    changed = [cid for cid in old.keys() & new.keys() if any(old[cid][k] != new[cid][k]
        for k in ('output', 'raw_model_decision', 'model_state_sha256'))]
    return {'controls_match': controls, 'changed_decision_case_ids': sorted(changed),
            'equivalent_behavior': controls and not changed, 'reference_timing_reused': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    args = parser.parse_args()
    result = verify(args.run)
    print(json.dumps(result, indent=2))
    return 0 if result['equivalent_behavior'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
