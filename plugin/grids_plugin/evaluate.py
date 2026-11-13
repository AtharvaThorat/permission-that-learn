"""Test the plugin's pipeline on the team's dataset `siddharth-magesh/grids-laya-permission-v1` (gated).

150 short user requests, each with one proposed tool call (Workspace, Slack, Banking), labelled ALLOW, ASK or BLOCK.

1. **Gatekeeper.** Each row's `laya_input` goes through the plugin's own `Scanner.decide` (laya-cybersec, rotated
   ALLOW / ASK / BLOCK, the question pinned by the dataset) and the plugin gate's mapping to a controller decision.
   Compared with the dataset's `source_label` and with the team's `reviewed_label`
   (`experiments/reference/permission-memory/reviewed_labels.csv`). Both label sets are LLM-made, not ground truth.
2. **Reproduction.** The decisions are compared with the team's recorded run on the same rows
   (`experiments/reference/permission-memory/laya_cybersec_rotated_predictions.jsonl`).
3. **Permission memory.** Two passes over the rows through the repository's `PermissionStore` (the team's scoped
   grants) with a simulated careful user who follows the reviewed label: in pass 1 every eligible ask goes to the user,
   who approves and remembers ALLOW / ASK rows and rejects BLOCK rows; in pass 2 the same requests are asked again.
   Counts questions, questions saved by grants, and any grant that would run a BLOCK-labelled action.

    hf auth login                   # once; the dataset is gated
    python -m grids_plugin.evaluate --laya-cache D:\\grids-plugin\\hf-cache --data D:\\grids-plugin\\data --output D:\\grids-plugin\\eval\\run-01

Nothing is executed: no tool runs and no chat model is called.
"""
import argparse
import csv
import hashlib
import json
import platform
import statistics
import time
from collections import Counter
from pathlib import Path

DATASET = 'siddharth-magesh/grids-laya-permission-v1'
DATASET_REVISION = '9659e4519fb3c9d96f899c777dfc55bdf299d563'      # the revision of the team's recorded run
PAIRS_FILE, METADATA_FILE = 'data/laya-pairs-v1.jsonl', 'metadata/laya-pairs-v1.json'
PAIRS_SHA256 = '78560d3ffce82ebbc1c78bc411b106029d9d7c0203b5db6f0b2665d6fd654c68'
QUESTION_SHA256 = '0ea28ad8b74e02a78a38ac926ea3044c6a64c723d7d78a3f171593b9c537f69b'
LABELS = ('ALLOW', 'ASK', 'BLOCK')


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def question_hash(question):
    return hashlib.sha256(json.dumps(question, sort_keys=True).encode()).hexdigest()


def download(data_dir, revision=DATASET_REVISION):
    """The two dataset files at a pinned revision. Needs a Hugging Face login with the dataset terms accepted."""
    from huggingface_hub import hf_hub_download
    return [Path(hf_hub_download(DATASET, name, repo_type='dataset', revision=revision, local_dir=str(data_dir)))
            for name in (PAIRS_FILE, METADATA_FILE)]


def load(pairs_path, metadata_path):
    rows = [json.loads(line) for line in Path(pairs_path).read_text(encoding='utf-8').splitlines() if line.strip()]
    metadata = json.loads(Path(metadata_path).read_text(encoding='utf-8'))
    return rows, metadata


def reviewed_labels():
    from grids.evaluation.permission_sim import LABELS as path   # the team's file, wherever the repository keeps it
    with open(path, encoding='utf-8-sig', newline='') as handle:
        return {row['id']: row for row in csv.DictReader(handle)}


def recorded_predictions():
    from grids.evaluation.permission_sim import PREDICTIONS as path
    lines = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    return lines[0]['header'], {row['id']: row for row in lines[1:]}


def controller_decision(result):
    """The plugin gate's mapping (guard.CybersecGate): what the controller receives for this row."""
    from .guard import REASONS
    if result['error']:
        return 'ASK', 'MODEL_UNAVAILABLE'
    if result['tie']:
        return 'ASK', 'UNCERTAIN'
    return result['decision'], REASONS[result['decision']]


def agreement(predicted, labels):
    pairs = [(predicted[i], labels[i]) for i in predicted if i in labels]
    confusion = {label: Counter(p for p, t in pairs if t == label) for label in LABELS}
    return {'rows': len(pairs), 'agree': sum(p == t for p, t in pairs),
            'agreement': round(sum(p == t for p, t in pairs) / len(pairs), 4) if pairs else None,
            'harmful_allows': sum(p == 'ALLOW' and t == 'BLOCK' for p, t in pairs),
            'false_blocks': sum(p == 'BLOCK' and t == 'ALLOW' for p, t in pairs),
            'confusion': {label: {p: confusion[label][p] for p in LABELS} for label in LABELS}}


def memory_replay(rows, decisions, labels, store_path):
    """Two passes through the repository's PermissionStore with a careful user who follows `labels`."""
    from grids.core.permissions.bindings import Binding
    from grids.core.permissions.memory import ELIGIBLE_REASONS
    from grids.core.permissions.store import PermissionStore
    store, user = PermissionStore(store_path), 'evaluation-user'
    by_id = {row['id']: row for row in rows}
    passes = []
    for number in (1, 2):
        counts = Counter()
        for row_id, (decision, reason, probabilities) in sorted(decisions.items()):
            if decision != 'ASK':
                continue
            counts['asks'] += 1
            if reason not in ELIGIBLE_REASONS or probabilities is None:
                counts['asked_person_forced'] += 1   # model failures never use memory
                continue
            row = by_id[row_id]
            arguments = row['tool_arguments'] if isinstance(row['tool_arguments'], dict) else json.loads(row['tool_arguments'])
            scope = {'request': row['user_prompt'], 'tool': row['tool_name'], 'arguments': arguments,
                     'facts': {'suite': row['suite']}, 'policy_version': 'laya-pairs-v1', 'schema_digest': row['suite']}
            binding = Binding('evaluation', f'pass-{number}', row_id, row_id, 'laya-pairs-v1', f'pass-{number}',
                              row['suite'], time.time() + 3600)
            decision_id, permit, _ = store.decide(user, scope, binding, probabilities, [], mode='grants')
            label = labels.get(row_id)
            if permit:
                counts['answered_by_grant'] += 1
                counts['grant_ran_block_labelled'] += label == 'BLOCK'
                continue
            counts['asked_person'] += 1
            approve = label in ('ALLOW', 'ASK')
            store.operational(user, decision_id, approve)
            if approve:
                store.issue(user, scope)
                counts['remembered'] += 1
            else:
                counts['rejected'] += 1
        passes.append({'pass': number, **{k: counts[k] for k in ('asks', 'asked_person', 'answered_by_grant',
                       'asked_person_forced', 'remembered', 'rejected', 'grant_ran_block_labelled')}})
    return passes


def evaluate(scanner, rows, metadata, output, store_path=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    question = metadata['laya_question']
    reviewed = {i: r['reviewed_label'] for i, r in reviewed_labels().items()}
    source = {row['id']: row['source_label'] for row in rows}
    header, recorded = recorded_predictions()
    records, decisions = [], {}
    cpu_started, wall_started = time.process_time(), time.perf_counter()
    for row in sorted(rows, key=lambda r: r['id']):
        result = scanner.decide(row['laya_input'], profile='recorded_full')
        decision, reason = controller_decision(result)
        decisions[row['id']] = (decision, reason, result['probabilities'])
        records.append({'id': row['id'], 'suite': row['suite'], 'difficulty': row.get('estimated_difficulty'),
                        'tool': row['tool_name'], 'source_label': row['source_label'],
                        'reviewed_label': reviewed.get(row['id']), 'model_decision': result['decision'],
                        'decision': decision, 'reason': reason, 'probabilities': result['probabilities'],
                        'error': result['error'], 'seconds': round(result['seconds'], 4),
                        'state_tokens': result['state_tokens'], 'sequence_tokens': result['sequence_tokens']})
    cpu_seconds, total_seconds = time.process_time() - cpu_started, time.perf_counter() - wall_started
    predicted = {r['id']: r['decision'] for r in records}
    same = [r for r in records if r['id'] in recorded]
    times = [r['seconds'] for r in records]
    summary = {
        'dataset': {'repo': DATASET, 'revision': DATASET_REVISION, 'rows': len(rows),
                    'pairs_sha256': metadata.get('_pairs_sha256'), 'question_sha256': question_hash(question),
                    'question_matches_plugin_gate': question_hash(question) == QUESTION_SHA256},
        'gatekeeper': {'model': scanner.model_id, 'revision': scanner.revision, 'method': 'single-v1-rotated',
                       'device': scanner.device, 'decisions': dict(Counter(predicted.values())),
                       'errors': sum(r['error'] is not None for r in records),
                       'ties': sum(r['reason'] == 'UNCERTAIN' for r in records)},
        'vs_reviewed_labels': agreement(predicted, reviewed),
        'vs_source_labels': agreement(predicted, source),
        'by_suite_reviewed': {suite: agreement({i: p for i, p in predicted.items() if by_suite[i] == suite}, reviewed)
                              for by_suite in [{r['id']: r['suite'] for r in records}]
                              for suite in sorted(set(by_suite.values()))},
        'reproduction': {'recorded_rows': len(same), 'recorded_packages': header.get('packages'),
                         'same_decision': sum(recorded[r['id']]['decision'] == r['model_decision'] for r in same),
                         'max_probability_difference': round(max(
                             (abs(recorded[r['id']]['probabilities'][k] - r['probabilities'][k])
                              for r in same if r['probabilities'] and recorded[r['id']].get('probabilities') for k in LABELS),
                             default=0.0), 6)},
        'compute': {'rows': len(records), 'total_seconds': round(total_seconds, 2), 'cpu_seconds': round(cpu_seconds, 2),
                    'mean_seconds': round(statistics.mean(times), 4), 'median_seconds': round(statistics.median(times), 4),
                    'p95_seconds': round(sorted(times)[max(0, int(0.95 * len(times)) - 1)], 4),
                    'max_sequence_tokens': max((r['sequence_tokens'] or 0) for r in records),
                    'load_seconds': round(scanner.load_seconds, 2), 'cpu': platform.processor() or platform.machine()},
        'memory_replay': memory_replay(rows, decisions, reviewed, store_path or output / 'permissions.sqlite'),
    }
    (output / 'predictions.jsonl').write_text('\n'.join(json.dumps(r, sort_keys=True) for r in records) + '\n', encoding='utf-8')
    (output / 'summary.json').write_text(json.dumps(summary, indent=1) + '\n', encoding='utf-8')
    (output / 'report.md').write_text(report(summary), encoding='utf-8')
    return summary


def table(confusion):
    lines = ['| Label \\ decision | ALLOW | ASK | BLOCK |', '|---|---:|---:|---:|']
    lines += [f'| {label} | ' + ' | '.join(str(confusion[label][p]) for p in LABELS) + ' |' for label in LABELS]
    return '\n'.join(lines)


def report(s):
    r, src, c, rep = s['vs_reviewed_labels'], s['vs_source_labels'], s['compute'], s['reproduction']
    replay = '\n'.join(f"| {p['pass']} | {p['asks']} | {p['asked_person']} | {p['answered_by_grant']} | "
                       f"{p['grant_ran_block_labelled']} |" for p in s['memory_replay'])
    suites = '\n'.join(f"| {suite} | {a['rows']} | {a['agree']} | {a['harmful_allows']} |"
                       for suite, a in s['by_suite_reviewed'].items())
    return f"""# Plugin pipeline on {s['dataset']['repo']}

Dataset revision `{s['dataset']['revision'][:7]}`, {s['dataset']['rows']} rows. Question matches the plugin's live gate:
**{s['dataset']['question_matches_plugin_gate']}**. Gatekeeper: `{s['gatekeeper']['model']}@{s['gatekeeper']['revision'][:7]}`,
{s['gatekeeper']['method']}, {s['gatekeeper']['device']}. Decisions: {s['gatekeeper']['decisions']}; errors
{s['gatekeeper']['errors']}; ties {s['gatekeeper']['ties']}.

## Agreement

| Labels | Agree | Harmful allows (BLOCK label → ALLOW) | False blocks (ALLOW label → BLOCK) |
|---|---:|---:|---:|
| Reviewed (team, LLM-made) | {r['agree']}/{r['rows']} | {r['harmful_allows']} | {r['false_blocks']} |
| Source (dataset, provisional) | {src['agree']}/{src['rows']} | {src['harmful_allows']} | {src['false_blocks']} |

Reviewed labels:

{table(r['confusion'])}

| Suite | Rows | Agree (reviewed) | Harmful allows |
|---|---:|---:|---:|
{suites}

## Reproduction of the team's recorded run

{rep['same_decision']}/{rep['recorded_rows']} same decisions; largest probability difference {rep['max_probability_difference']}
(recorded with {rep['recorded_packages']}).

## Compute (CPU)

{c['rows']} rows in {c['total_seconds']} s ({c['cpu_seconds']} CPU-seconds): mean {c['mean_seconds']} s, median
{c['median_seconds']} s, p95 {c['p95_seconds']} s per row; longest input {c['max_sequence_tokens']} tokens of 1,024;
model load {c['load_seconds']} s. One model call per row answers all three option orders.

## Permission memory replay (repository PermissionStore, careful user following reviewed labels)

| Pass | Asks | Asked the user | Answered by a remembered permission | Grant ran a BLOCK-labelled action |
|---:|---:|---:|---:|---:|
{replay}

Only the model's asks reach memory; ALLOW and BLOCK decisions bypass it. A grant covers the exact request and action.
"""


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--laya-cache', required=True, help='folder with (or for) the laya-cybersec download')
    parser.add_argument('--data', required=True, help='folder for the dataset files (downloaded if missing)')
    parser.add_argument('--output', required=True, help='new folder for predictions.jsonl, summary.json and report.md')
    parser.add_argument('--laya-device', default='cpu', choices=['cpu', 'cuda'])
    args = parser.parse_args(argv)
    data = Path(args.data)
    pairs, metadata_path = data / PAIRS_FILE, data / METADATA_FILE
    if not (pairs.is_file() and metadata_path.is_file()):
        pairs, metadata_path = download(data)
    if sha256(pairs) != PAIRS_SHA256:
        print(f'Note: {pairs.name} differs from the team\'s recorded file (sha256 {PAIRS_SHA256[:8]}).')
    rows, metadata = load(pairs, metadata_path)
    metadata['_pairs_sha256'] = sha256(pairs)
    if question_hash(metadata['laya_question']) != QUESTION_SHA256:
        print('Note: the dataset question differs from the plugin gate\'s question; the dataset question is used.')
    from .cybersec import MODEL_ID, REVISION, Scanner, download as download_model
    scanner = Scanner(download_model(args.laya_cache), device=args.laya_device, question=metadata['laya_question'])
    scanner.model_id, scanner.revision = MODEL_ID, REVISION
    summary = evaluate(scanner, rows, metadata, args.output)
    print(report(summary))
    print(f'Written to {args.output}')


if __name__ == '__main__':
    main()
