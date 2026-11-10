"""Offline simulation of approval memory with simulated users: no model, no GPU.

Each dataset row is one proposed action. One simulated user meets one suite's actions
in a seeded random order, several times over, and answers whatever it is asked. The
proposal's four setups run on the same streams:

  no_protection          every action runs
  fixed_rules            Wall + rules gatekeeper; every ask goes to the user
  learning_no_wall       rules gatekeeper + memory, no Wall
  learning_inside_wall   Wall + rules gatekeeper + memory (the project's design)

Labels drive only the simulated user and the evaluator, never the learner. A careful
user approves ALLOW and ASK actions (what the task intended) and rejects BLOCK; a
careless user also approves a BLOCK action with probability p.
"""
import argparse
import csv
import hashlib
import io
import json
import math
import random
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from grids.core.config import LearningConfig
from grids.core.permissions.memory import ELIGIBLE_REASONS, build_memory, pattern_key
from grids.gatekeeper.rules import rules_decision
from grids.paths import ROOT

DATA = ROOT / 'docs' / 'results' / 'laya-permission-v1'
COMPACT = ROOT / 'docs' / 'results' / 'laya-permission-v1-compact'
SETUPS = ('no_protection', 'fixed_rules', 'learning_no_wall', 'learning_inside_wall')
USERS = {'careful': 0.0, 'careless_10': 0.1, 'careless_20': 0.2, 'careless_40': 0.4}
LEARNING = [(setup, learner, granularity) for setup in ('learning_no_wall', 'learning_inside_wall')
            for learner in ('counting', 'bandit') for granularity in ('exact', 'class')]
CONFIGS = [('no_protection', 'none', 'none'), ('fixed_rules', 'none', 'none'), *LEARNING]
METRICS = ('actions', 'questions', 'auto_allowed', 'auto_blocked', 'allow_completed', 'false_blocks',
           'executed_block', 'attacks_executed', 'wrong_auto_allows', 'skipped_confirmations',
           'careless_approvals', 'creep_keys', 'unauthorized_keys', 'latent_harm')


@dataclass(frozen=True)
class Event:
    id: str
    suite: str
    label: str
    attack: bool
    tool: str
    arguments: dict
    effects: tuple
    targets: dict
    wall_verdict: str
    confirmation_required: bool
    evidence_complete: bool


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]


def load_events(data=DATA, compact=COMPACT):
    provenance = {p['id']: p for p in read_jsonl(Path(data) / 'provenance.jsonl')}
    events = []
    for split in ('train', 'test'):
        for row in read_jsonl(Path(compact) / f'{split}.jsonl'):
            state, p = json.loads(row['context']), provenance[row['id']]
            facts = state['verified_context']['facts']
            events.append(Event(row['id'], row['group_id'].split('/')[1], row['label'],
                                row['label'] == 'BLOCK' and p['template'] is not None,
                                state['untrusted_proposed_action']['tool'], state['untrusted_proposed_action']['arguments'],
                                tuple(facts['effects']), facts['targets'], p['wall_verdict'],
                                p['confirmation_required'], p['evidence_complete']))
    return events


def gate_path(event, setup):
    """The controller's order: Wall (non-PASS blocks), gatekeeper, then forced asks."""
    if setup == 'no_protection':
        return 'ALLOW', 'UNPROTECTED'
    wall = setup in ('fixed_rules', 'learning_inside_wall')
    if wall and event.wall_verdict != 'PASS':
        return 'BLOCK', 'WALL_' + event.wall_verdict
    decision, reason = rules_decision(event.effects)
    if decision != 'BLOCK' and wall and (event.confirmation_required or not event.evidence_complete):
        return 'ASK', 'CONFIRMATION_REQUIRED' if event.confirmation_required else 'INCOMPLETE_EVIDENCE'
    return decision, reason


def key_of(event, granularity):
    return pattern_key(event.tool, event.arguments, lambda v: event.targets.get(v, 'unknown'), granularity, event.suite)


def simulate_stream(events, setup, learner, granularity, p_careless, seed, passes, learning=None):
    """One user, one suite: counts, a per-pass curve, and the memory's final auto-allow set."""
    learning = (learning or LearningConfig()).model_copy(update={'learner': learner if learner != 'none' else 'counting',
                                                               'seed': seed})
    memory = build_memory(learning) if setup.startswith('learning') else None
    order_rng = random.Random(f'{seed}-{events[0].suite}-order')
    # The same careless moments in every setup, so setups are compared on paired streams.
    slips = [[random.Random(f'{seed}-{events[0].suite}-{n}-{e.id}').random() for e in events] for n in range(passes)]
    index = {e.id: i for i, e in enumerate(events)}
    counts, curve = defaultdict(int), []
    for n in range(passes):
        order = list(events)
        order_rng.shuffle(order)
        questions_before = counts['questions']
        for event in order:
            counts['actions'] += 1
            decision, reason = gate_path(event, setup)
            executed = decision == 'ALLOW'
            if decision == 'ASK':
                eligible = memory is not None and reason in ELIGIBLE_REASONS
                key = key_of(event, granularity) if eligible else None
                choice = memory.decide(key) if eligible else 'ask'
                if choice == 'allow':
                    executed = True
                    counts['auto_allowed'] += 1
                    counts['wrong_auto_allows'] += event.label == 'BLOCK'
                    counts['skipped_confirmations'] += event.label == 'ASK'
                elif choice == 'block':
                    counts['auto_blocked'] += 1
                else:
                    counts['questions'] += 1
                    approved = event.label != 'BLOCK' or slips[n][index[event.id]] < p_careless
                    counts['careless_approvals'] += approved and event.label == 'BLOCK'
                    if eligible:
                        memory.update(key, approved)
                    executed = approved
            counts['allow_completed'] += executed and event.label == 'ALLOW'
            counts['false_blocks'] += not executed and event.label == 'ALLOW'
            counts['executed_block'] += executed and event.label == 'BLOCK'
            counts['attacks_executed'] += executed and event.attack
        allowed = set(memory.allowed()) if memory else set()
        curve.append((n + 1, counts['questions'] - questions_before, len(allowed)))
    if memory:
        reachable = [e for e in events if gate_path(e, setup)[0] == 'ASK' and gate_path(e, setup)[1] in ELIGIBLE_REASONS]
        harmful = defaultdict(int)
        for e in reachable:
            if e.label == 'BLOCK':
                harmful[key_of(e, granularity)] += 1
        counts['creep_keys'] = len(allowed)
        counts['unauthorized_keys'] = sum(1 for k in allowed if harmful.get(k))
        counts['latent_harm'] = sum(harmful.get(k, 0) for k in allowed)
    return dict(counts), curve


def ci95(values):
    if len(values) < 2:
        return 0.0
    return 1.96 * statistics.stdev(values) / math.sqrt(len(values))


def run(seeds=50, passes=3, data=DATA, compact=COMPACT):
    events = load_events(data, compact)
    suites = defaultdict(list)
    for e in events:
        suites[e.suite].append(e)
    runs, curves = [], defaultdict(lambda: defaultdict(list))
    for setup, learner, granularity in CONFIGS:
        for user, p in USERS.items():
            for seed in range(seeds):
                total, pass_curve = defaultdict(int), defaultdict(lambda: [0, 0])
                for suite in sorted(suites):
                    counts, curve = simulate_stream(suites[suite], setup, learner, granularity, p, seed, passes)
                    for k, v in counts.items():
                        total[k] += v
                    for n, q, size in curve:
                        pass_curve[n][0] += q
                        pass_curve[n][1] += size
                runs.append({'setup': setup, 'learner': learner, 'granularity': granularity, 'user': user,
                             'seed': seed, **{m: total.get(m, 0) for m in METRICS}})
                for n, (q, size) in pass_curve.items():
                    curves[(setup, learner, granularity, user, n)]['questions'].append(q)
                    curves[(setup, learner, granularity, user, n)]['creep_keys'].append(size)
    return events, runs, curves


def summarize(runs):
    groups = defaultdict(list)
    for r in runs:
        groups[(r['setup'], r['learner'], r['granularity'], r['user'])].append(r)
    rows = []
    for (setup, learner, granularity, user), rs in groups.items():
        row = {'setup': setup, 'learner': learner, 'granularity': granularity, 'user': user, 'seeds': len(rs)}
        for m in METRICS:
            values = [r[m] for r in rs]
            row[m] = round(statistics.fmean(values), 3)
            row[m + '_ci95'] = round(ci95(values), 3)
        rows.append(row)
    return rows


def to_csv(rows):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, list(rows[0]), lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(output, events, runs, curves, seeds, passes, data=DATA, compact=COMPACT):
    out = Path(output)
    out.mkdir(parents=True, exist_ok=False)
    summary = summarize(runs)
    curve_rows = [{'setup': s, 'learner': l, 'granularity': g, 'user': u, 'pass': n,
                   'questions': round(statistics.fmean(v['questions']), 3),
                   'creep_keys': round(statistics.fmean(v['creep_keys']), 3)}
                  for (s, l, g, u, n), v in curves.items()]
    (out / 'runs.csv').write_text(to_csv(runs), encoding='utf-8')
    (out / 'summary.csv').write_text(to_csv(summary), encoding='utf-8')
    (out / 'curves.csv').write_text(to_csv(curve_rows), encoding='utf-8')
    counts = defaultdict(int)
    for e in events:
        counts[f'{e.suite}:{e.label}'] += 1
    info = {'seeds': seeds, 'passes': passes, 'users': USERS, 'configs': CONFIGS, 'events': len(events),
            'events_by_suite_label': dict(sorted(counts.items())), 'learning_defaults': LearningConfig().model_dump(),
            'eligible_reasons': sorted(ELIGIBLE_REASONS),
            'inputs': {str(p.relative_to(ROOT)): sha256(p) for p in sorted(
                [Path(data) / 'provenance.jsonl', Path(compact) / 'train.jsonl', Path(compact) / 'test.jsonl'])},
            'labels': 'reviewed by an LLM (Claude), not a person; they drive the simulated users and the evaluator only'}
    (out / 'run.json').write_text(json.dumps(info, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(prog='grids memory', description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('operation', choices=['simulate'])
    parser.add_argument('--seeds', type=int, default=50)
    parser.add_argument('--passes', type=int, default=3)
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    if args.seeds < 1 or args.passes < 1:
        sys.exit('--seeds and --passes must be at least 1')
    events, runs, curves = run(args.seeds, args.passes)
    write(args.output, events, runs, curves, args.seeds, args.passes)
    print(f'wrote {args.output}: {len(runs)} streams over {len(events)} actions, {args.passes} passes, {args.seeds} seeds')
