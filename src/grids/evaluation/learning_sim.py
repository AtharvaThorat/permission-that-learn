"""Learning simulation on synthetic users: memory baselines versus per-user contextual policies.

Every arm sees the same timeline, the same pre-drawn user answers and the same careless moments. The gate in
front of the arms is the live decision order (`permission_sim.gate_path`): Wall, then gatekeeper BLOCK,
forced asks, gatekeeper ALLOW, and only then a judgment ask that an arm may answer.

Arms:
  no_memory            every judgment ask reaches the user
  counting_exact       auto-allow after 2 approvals, auto-block after 1 rejection (the old baseline)
  grants               an offer after 2 approvals; only an explicit user grant allows
  grants_deny          grants, plus a rejected exact pattern is refused without asking (tightens only)
  <rule>_free          the contextual policy alone may allow (rule: linucb, lints, egreedy)
  <rule>_guarded       the policy may allow only inside a live grant; it also times the grant offers
  linucb_guarded_deny  the guarded design plus remembered rejections
  linucb_pooled        one policy shared by all users: the cross-user contamination reference

Gatekeepers: `laya` (recorded predictions decide), `rules` (reads allowed, destructive blocked, every other
action asked; no model), and `advised` (the rules decide, and Laya's probabilities are only context for the
policies). `oracle` (the label decides) exists for sanity tests.

Simulated user: answers an ask with the row's pre-drawn answer; a careless user (p) also approves an unwanted
action with probability p, accepts a grant offer whose scope is not routine with probability p, and then picks
the broad (trust-class) scope with probability p. A careful user judges the scope, not the single action, and
knows their own standing preferences: an offer is accepted only if every recurring request of theirs that the
exact pattern covers is one they approve at least 90% of the time at that moment, and only with exact scope.
Nobody can foresee an agent error or an attack that copies a routine action.
Labels, kinds and preferences drive the simulated user and the metrics, never an arm.
"""
import json
import random
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from grids.core.permissions.contextual import FEATURES, RULES, ContextualMemory, ContextualPolicy
from grids.core.permissions.memory import CountingMemory, GrantStore
from .learning_data import gate_of, load_input_predictions
from .memory_sim import ci95, read_jsonl, sha256, to_csv
from .permission_sim import gate_path, key_of

ARMS = ('no_memory', 'counting_exact', 'grants', 'grants_deny', 'linucb_free', 'lints_free', 'egreedy_free',
        'linucb_guarded', 'lints_guarded', 'egreedy_guarded', 'linucb_guarded_deny', 'linucb_pooled')
USERS = {'careful': 0.0, 'careless_10': 0.1, 'careless_20': 0.2, 'careless_40': 0.4}
METRICS = ('actions', 'questions', 'cold_start_questions', 'auto_allowed', 'auto_blocked', 'wrong_auto_allows',
           'attacks_auto_allowed', 'skipped_confirmations', 'allows_without_grant', 'poisoned_auto_allows',
           'drift_wrong_allows', 'drift_questions', 'executed', 'unwanted_executed', 'attacks_executed',
           'false_blocks', 'auto_false_blocks', 'careless_approvals', 'grant_offers', 'grants_issued',
           'broad_grants', 'unwanted_grants')
ROUTINE = 0.9
COLD_START = 50
VERSION = 'workspace'


def load_events(world, predictions=None, gatekeeper='laya'):
    """Stream rows in time order with the recorded gate output and the pattern keys every arm shares."""
    rows = sorted(read_jsonl(Path(world) / 'stream.jsonl'), key=lambda r: (r['t'], r['user']))
    # The user's own recurring requests behind each exact pattern, with the preference they hold over time.
    preferences, explicit = defaultdict(dict), set()
    for row in rows:
        scope = (row['user'], key_of(row, 'exact'))
        if row['kind'] == 'ask':
            preferences[scope].setdefault(row['pattern'], []).append((row['t'], row['approve_probability']))
        elif row['kind'] == 'allow':
            explicit.add(scope)
    events = []
    for row in rows:
        event = dict(row)
        if gatekeeper == 'oracle':
            gate = {'decision': row['label'], 'probabilities': None, 'unanimous': False}
        elif predictions is None:
            gate = {'decision': None, 'probabilities': None, 'unanimous': False}
        else:
            gate = gate_of(row, predictions)
        event['laya'] = gate['decision']
        event['exact'], event['broad'] = key_of(row, 'exact'), key_of(row, 'class')
        # What a careful person weighs when offered a standing permission for this exact pattern: do they
        # routinely want every request of theirs it covers, as of now?
        scope = (row['user'], event['exact'])
        held = [next((p for t, p in reversed(history) if t <= row['t']), history[0][1])
                for history in preferences[scope].values()]
        event['routine_scope'] = min(held) >= ROUTINE if held else scope in explicit
        event['context'] = {'probabilities': gate['probabilities'], 'unanimous': gate['unanimous'],
                            'effects': row['effects'], 'reach': row['reach']}
        events.append(event)
    return events


def parse_arm(arm):
    rule, _, mode = arm.partition('_')
    return (rule, mode) if rule in RULES else (None, None)


def simulate(events, arm, wall, gatekeeper, p_careless, seed, settings=None, log=None):
    """One pass of all users through their timelines under one arm. Returns {(group, metric): count}.

    `log`, if given, receives one record per row: who decided (`gate`, `memory` or `user`), whether it ran,
    and for user answers the approval, any offer and the granted scope. It is the feedback log.
    """
    if arm not in ARMS:
        raise ValueError(f'Unknown arm: {arm}')
    rule, mode = parse_arm(arm)
    guarded = mode in ('guarded', 'guarded_deny')
    memory = ContextualMemory(rule, pooled=mode == 'pooled', seed=seed, **(settings or {})) if rule else None
    counting, stores, offered = {}, {}, defaultdict(set)
    deny = arm in ('grants_deny', 'linucb_guarded_deny')
    slip = lambda kind, e: random.Random(f'{seed}|{kind}|{e["id"]}').random() < p_careless
    counts = defaultdict(int)
    for e in events:
        user, group, wanted = e['user'], e['group'], e['user_answer']
        decision, reason = gate_path(e, wall, 'rules' if gatekeeper in ('rules', 'advised') else 'laya')
        executed = decision == 'ALLOW'
        record = {'id': e['id'], 'user': user, 't': e['t'], 'source': 'gate', 'reason': reason}
        if decision == 'ASK':
            eligible = reason == 'NEEDS_CLARIFICATION'
            exact, broad, context = e['exact'], e['broad'], e['context']
            store = stores.setdefault(user, GrantStore(offer_after=2, remember_rejections=deny))
            auto = 'ask'
            if eligible and arm == 'counting_exact':
                auto = counting.setdefault(user, CountingMemory(approvals_to_allow=2)).decide(exact)
            elif eligible and arm in ('grants', 'grants_deny'):
                auto = 'block' if store.denies(exact) else 'allow' if store.covers(exact, broad) else 'ask'
            elif eligible and guarded:
                if store.denies(exact):
                    auto = 'block'
                elif store.covers(exact, broad):
                    auto = memory.decide(user, VERSION, exact, broad, context)
            elif eligible and memory is not None:
                auto = memory.decide(user, VERSION, exact, broad, context)
            if auto != 'ask':
                record['source'] = 'memory'
            if auto == 'allow':
                executed = True
                counts[group, 'auto_allowed'] += 1
                counts[group, 'wrong_auto_allows'] += not wanted
                counts[group, 'attacks_auto_allowed'] += e['attack']
                counts[group, 'skipped_confirmations'] += e['label'] == 'ASK' and wanted
                counts[group, 'allows_without_grant'] += memory is not None and not guarded
                counts[group, 'poisoned_auto_allows'] += e['poison']
                counts[group, 'drift_wrong_allows'] += e['after_drift'] and not wanted
            elif auto == 'block':
                counts[group, 'auto_blocked'] += 1
                counts[group, 'auto_false_blocks'] += wanted
            else:
                counts[group, 'questions'] += 1
                counts[group, 'cold_start_questions'] += e['t'] < COLD_START
                counts[group, 'drift_questions'] += e['after_drift']
                approved = wanted or slip('approve', e)
                counts[group, 'careless_approvals'] += approved and not wanted
                executed = approved
                offer, granted = False, None
                if eligible:
                    if arm == 'counting_exact':
                        counting[user].update(exact, approved)
                    elif memory is None and arm != 'no_memory':
                        offer = store.record(exact, approved, broad)
                    elif memory is not None:
                        memory.update(user, VERSION, exact, broad, context, approved)
                        if guarded:
                            store.record(exact, approved, broad)
                            if not approved:
                                offered[user].discard(exact)
                            # The policy, not a fixed count, decides when a standing permission is worth offering.
                            elif exact not in offered[user] and memory.confident(user, VERSION, exact, broad, context):
                                offer = True
                                offered[user].add(exact)
                    if offer:
                        counts[group, 'grant_offers'] += 1
                        routine = e['routine_scope']
                        if routine or slip('grant', e):
                            granted = 'class' if slip('scope', e) else 'exact'
                            store.grant(exact if granted == 'exact' else broad, granted)
                            counts[group, 'grants_issued'] += 1
                            counts[group, 'broad_grants'] += granted == 'class'
                            counts[group, 'unwanted_grants'] += not routine
                record.update(source='user', eligible=eligible, approved=approved, offered=offer, granted=granted)
        counts[group, 'actions'] += 1
        if log is not None:
            log.append(dict(record, executed=executed))
        if executed:
            counts[group, 'executed'] += 1
            counts[group, 'unwanted_executed'] += not wanted
            counts[group, 'attacks_executed'] += e['attack']
        else:
            counts[group, 'false_blocks'] += wanted
    return dict(counts)


def rows_of(counts, **fields):
    """One row per user group plus their total."""
    groups = sorted({g for g, _ in counts})
    rows = []
    for group in groups + ['all']:
        pick = lambda m: sum(counts.get((g, m), 0) for g in (groups if group == 'all' else [group]))
        rows.append({**fields, 'group': group, **{m: int(pick(m)) for m in METRICS}})
    return rows


def _job(args):
    events, gatekeeper, wall, user, p, seeds, arms, settings = args
    rows = []
    for arm in arms:
        for seed in range(seeds):
            counts = simulate(events, arm, wall, gatekeeper, p, seed, settings)
            rows += rows_of(counts, gatekeeper=gatekeeper, wall=wall, arm=arm, user=user, seed=seed)
    return rows


def run(world, predictions_path, seeds=20, arms=ARMS, gatekeepers=('laya', 'rules', 'advised'), users=USERS,
        settings=None, workers=None):
    """Every arm, with and without the Wall, for each gatekeeper and user type. Deterministic per seed."""
    _, predictions = load_input_predictions(predictions_path)
    laya_events, rule_events = load_events(world, predictions), load_events(world)
    jobs = [(rule_events if g == 'rules' else laya_events, g, wall, user, p, seeds, arms, settings)
            for g in gatekeepers for wall in (True, False) for user, p in users.items()]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return [row for rows in pool.map(_job, jobs) for row in rows]


def summarize(runs, keys=('gatekeeper', 'wall', 'arm', 'user', 'group')):
    groups = defaultdict(list)
    for r in runs:
        groups[tuple(r[k] for k in keys)].append(r)
    out = []
    for key, rows in sorted(groups.items(), key=lambda kv: tuple(str(v) for v in kv[0])):
        row = dict(zip(keys, key), seeds=len(rows))
        for metric in METRICS:
            values = [r[metric] for r in rows]
            row[metric] = round(sum(values) / len(values), 3)
            row[metric + '_ci95'] = round(ci95(values), 3)
        out.append(row)
    return out


def gate_table(world, predictions_path):
    """What the gate does before any memory: label by decision path, with and without the Wall."""
    _, predictions = load_input_predictions(predictions_path)
    rows = []
    for gatekeeper, events in (('laya', load_events(world, predictions)), ('rules', load_events(world))):
        for wall in (True, False):
            table = defaultdict(int)
            for e in events:
                table[(e['kind'], e['label'], *gate_path(e, wall, gatekeeper))] += 1
            rows += [{'gatekeeper': gatekeeper, 'wall': wall, 'kind': kind, 'label': label, 'decision': decision,
                      'reason': reason, 'rows': n} for (kind, label, decision, reason), n in sorted(table.items())]
    return rows


def decision_cost(rule='linucb', updates=200, decisions=2000):
    """Rough microseconds per policy decision and per update on this machine (not part of the results)."""
    rng, policy = random.Random(0), ContextualPolicy(rule)
    vectors = [[1.0] + [rng.random() for _ in FEATURES[1:]] for _ in range(decisions)]
    started = time.perf_counter()
    for x in vectors[:updates]:
        policy.update(x, rng.random() < 0.8)
    middle = time.perf_counter()
    for x in vectors:
        policy.decide(x)
    return {'rule': rule, 'update_us': round((middle - started) / updates * 1e6, 1),
            'decide_us': round((time.perf_counter() - middle) / decisions * 1e6, 1)}


def sweep(world, predictions_path, seeds=10, alphas=(0.1, 0.3, 0.6, 1.0), taus=(0.8, 0.9, 0.95)):
    """Sensitivity of the LinUCB arms to the confidence width and the threshold (rules gatekeeper, Wall on)."""
    events, rows = load_events(world), []
    for alpha in alphas:
        for tau in taus:
            for arm in ('linucb_free', 'linucb_guarded'):
                for user in ('careful', 'careless_20'):
                    for seed in range(seeds):
                        counts = simulate(events, arm, True, 'rules', USERS[user], seed, {'alpha': alpha, 'tau': tau})
                        rows += [dict(r, alpha=alpha, tau=tau) for r in rows_of(
                            counts, gatekeeper='rules', wall=True, arm=arm, user=user, seed=seed)
                                 if r['group'] == 'all']
    return rows


def learn(world, predictions_path, output, seeds=20, sweep_seeds=10, workers=1):
    out = Path(output)
    out.mkdir(parents=True, exist_ok=False)
    header, _ = load_input_predictions(predictions_path)
    runs = run(world, predictions_path, seeds, workers=workers)
    (out / 'runs.csv').write_text(to_csv(runs), encoding='utf-8')
    (out / 'summary.csv').write_text(to_csv(summarize(runs)), encoding='utf-8')
    (out / 'gate.csv').write_text(to_csv(gate_table(world, predictions_path)), encoding='utf-8')
    if sweep_seeds:
        swept = sweep(world, predictions_path, sweep_seeds)
        (out / 'sweep.csv').write_text(to_csv(summarize(swept, ('alpha', 'tau', 'arm', 'user'))), encoding='utf-8')
    info = {'seeds': seeds, 'sweep_seeds': sweep_seeds, 'arms': ARMS, 'users': USERS, 'features': FEATURES,
            'policy_defaults': {'tau': 0.9, 'alpha': 0.3, 'epsilon': 0.1, 'audit': 0.02, 'ridge': 1.0},
            'counting': {'approvals_to_allow': 2, 'rejections_to_block': 1}, 'grant_offer_after': 2,
            'routine_threshold': ROUTINE, 'cold_start_events': COLD_START,
            'world': json.loads((Path(world) / 'spec.json').read_text(encoding='utf-8')),
            'predictions': {'file_sha256': sha256(predictions_path), 'header': header}}
    (out / 'run.json').write_text(json.dumps(info, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return info
