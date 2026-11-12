"""Local trusted-operator store. SQLite serializes grants, feedback and dispatch."""
from contextlib import contextmanager
from dataclasses import asdict
import json
import math
from pathlib import Path
import sqlite3
import time
from uuid import uuid4

from grids.core.actions import canonical, digest
from . import learning


def scope_for(request, action):
    return {'request': request, 'tool': action.tool, 'arguments': json.loads(action.arguments_json),
            'facts': json.loads(action.facts_json), 'policy_version': action.policy_version,
            'schema_digest': action.schema_digest}


class PermissionStore:
    def __init__(self, path, clock=time.time):
        self.path, self.clock, self.session = str(path), clock, uuid4().hex
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                raise ValueError('UNSUPPORTED_PERMISSION_SCHEMA')
            db.execute('CREATE TABLE IF NOT EXISTS grants (id TEXT PRIMARY KEY, user TEXT NOT NULL, scope TEXT NOT NULL, '
                       'created REAL, expires REAL, maximum INTEGER, uses INTEGER DEFAULT 0, version INTEGER DEFAULT 1, '
                       'revoked INTEGER DEFAULT 0)')
            db.execute('CREATE TABLE IF NOT EXISTS decisions (id TEXT PRIMARY KEY, user TEXT NOT NULL, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS reservations (id TEXT PRIMARY KEY, user TEXT, grant_id TEXT, '
                       'version INTEGER, binding TEXT, decision_id TEXT UNIQUE, session TEXT, dispatched INTEGER DEFAULT 0)')
            db.execute('CREATE TABLE IF NOT EXISTS learners (user TEXT PRIMARY KEY, state TEXT NOT NULL)')
            db.execute('CREATE UNIQUE INDEX IF NOT EXISTS reservation_binding ON reservations(user,binding)')
            db.execute('CREATE TABLE IF NOT EXISTS feedback (id TEXT PRIMARY KEY, decision_id TEXT UNIQUE, '
                       'user TEXT, data TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS audit (sequence INTEGER PRIMARY KEY, at REAL, event TEXT, data TEXT)')
            db.execute('PRAGMA user_version=1')

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def user(value):
        if not isinstance(value, str) or not value.strip() or len(value) > 200:
            raise ValueError('TRUSTED_USER_REQUIRED')
        return value

    def audit(self, db, event, data):
        db.execute('INSERT INTO audit(at,event,data) VALUES(?,?,?)', (self.clock(), event, canonical(data)))

    def issue(self, user, scope, ttl=86400, maximum=None):
        self.user(user)
        if (type(ttl) not in (int, float) or not math.isfinite(ttl) or ttl <= 0
                or maximum is not None and (type(maximum) is not int or maximum < 1)):
            raise ValueError('INVALID_GRANT_LIMITS')
        required = {'request', 'tool', 'arguments', 'facts', 'policy_version', 'schema_digest'}
        if set(scope) != required or not all(scope[k] for k in ('request', 'tool', 'policy_version', 'schema_digest')):
            raise ValueError('EXACT_SCOPE_REQUIRED')
        if not isinstance(scope['arguments'], dict) or not isinstance(scope['facts'], dict):
            raise ValueError('INVALID_SCOPE')
        grant_id = uuid4().hex
        with self.transaction() as db:
            db.execute('INSERT INTO grants(id,user,scope,created,expires,maximum) VALUES(?,?,?,?,?,?)',
                       (grant_id, user, canonical(scope), self.clock(), self.clock() + ttl, maximum))
            self.audit(db, 'grant_issued', {'user': user, 'grant_id': grant_id, 'scope_hash': digest(scope)})
        return grant_id

    def list(self, user):
        self.user(user)
        with self.transaction() as db:
            return [dict(r) for r in db.execute('SELECT * FROM grants WHERE user=? ORDER BY created,id', (user,))]

    def revoke(self, user, grant_id):
        with self.transaction() as db:
            count = db.execute('UPDATE grants SET revoked=1,version=version+1 WHERE user=? AND id=? AND revoked=0',
                               (self.user(user), grant_id)).rowcount
            self.audit(db, 'grant_revoked', {'user': user, 'grant_id': grant_id, 'changed': count})
        return bool(count)

    def matching(self, db, user, scope):
        return db.execute('SELECT * FROM grants WHERE user=? AND scope=? AND revoked=0 AND expires>? '
                          'AND (maximum IS NULL OR uses<maximum) ORDER BY created,id LIMIT 1',
                          (user, canonical(scope), self.clock())).fetchone()

    def state(self, db, user):
        row = db.execute('SELECT state FROM learners WHERE user=?', (user,)).fetchone()
        return json.loads(row['state']) if row else learning.initial()

    def save_state(self, db, user, state):
        db.execute('INSERT OR REPLACE INTO learners VALUES(?,?)', (user, canonical(state)))

    def decide(self, user, scope, binding, probabilities, effects, mode='shadow', frozen=False, metadata=None):
        self.user(user)
        if mode not in ('off', 'shadow', 'active', 'grants'):
            raise ValueError('INVALID_LEARNING_MODE')
        with self.transaction() as db:
            grant = self.matching(db, user, scope)
            state = self.state(db, user)
            x = learning.features(probabilities, scope['tool'], effects, scope['facts'],
                                  self.clock() - grant['created'] if grant else 0, state['reviewed'])
            recommendation, propensity = learning.choose(state, x, grant is not None, frozen)
            action = recommendation if mode == 'active' else 'ASK_USER'
            if mode == 'grants':
                action = 'USE_EXISTING_GRANT' if grant else 'ASK_USER'
            record = {'scope': scope, 'binding': asdict(binding), 'features': x, 'probabilities': probabilities,
                      'recommendation': recommendation, 'recommendation_probability': propensity,
                      'action': action, 'propensity': propensity if mode == 'active' else 1.,
                      'grant_id': grant['id'] if grant else None, 'mode': mode, 'frozen': frozen,
                      'learner_version': state['version'], 'feature_version': 1, 'operational_approval': None,
                      'outcome': None, 'gate_metadata': metadata}
            decision_id = uuid4().hex
            permit = None
            if action == 'USE_EXISTING_GRANT':
                permit = {'id': uuid4().hex, 'user': user, 'grant_id': grant['id'], 'version': grant['version'],
                          'expires_at': grant['expires']}
                db.execute('INSERT INTO reservations(id,user,grant_id,version,binding,decision_id,session) VALUES(?,?,?,?,?,?,?)',
                           (permit['id'], user, grant['id'], grant['version'], canonical(asdict(binding)), decision_id, self.session))
                db.execute('UPDATE grants SET uses=uses+1 WHERE id=?', (grant['id'],))
            db.execute('INSERT INTO decisions VALUES(?,?,?)', (decision_id, user, canonical(record)))
            if not frozen and mode in ('shadow', 'active'):
                if action == 'ASK_USER':
                    learning.update(state, action, x, 1.)
                self.save_state(db, user, state)
            self.audit(db, 'decision', {'user': user, 'decision_id': decision_id, 'action': action})
            return decision_id, permit, record

    def operational(self, user, decision_id, approved):
        with self.transaction() as db:
            row = db.execute('SELECT data FROM decisions WHERE id=? AND user=?', (decision_id, user)).fetchone()
            record = json.loads(row['data'])
            record['operational_approval'] = approved
            db.execute('UPDATE decisions SET data=? WHERE id=?', (canonical(record), decision_id))
            if approved is False:
                db.execute('UPDATE grants SET revoked=1,version=version+1 WHERE user=? AND scope=? AND revoked=0',
                           (user, canonical(record['scope'])))
            self.audit(db, 'operational_feedback', {'user': user, 'decision_id': decision_id, 'approved': approved})

    def outcome(self, user, decision_id, outcome):
        with self.transaction() as db:
            row = db.execute('SELECT data FROM decisions WHERE id=? AND user=?', (decision_id, user)).fetchone()
            record = json.loads(row['data'])
            # Native result objects remain in the existing conversation/trace artifacts.
            record['outcome'] = {name: getattr(outcome, name) for name in
                                 ('executed', 'reason', 'decision', 'error', 'terminal', 'state_version')}
            db.execute('UPDATE decisions SET data=? WHERE id=?', (canonical(record), decision_id))
            self.audit(db, 'outcome', {'decision_id': decision_id, 'executed': outcome.executed})

    @contextmanager
    def dispatch_guard(self, permit, binding):
        # Reservation is already durable. Keep the write lock through dispatch: a committed
        # revocation always wins over a later invocation, even from another process.
        with self.transaction() as db:
            r = db.execute('SELECT * FROM reservations WHERE id=?', (permit['id'],)).fetchone()
            g = db.execute('SELECT * FROM grants WHERE id=? AND user=?',
                           (permit['grant_id'], permit['user'])).fetchone()
            if (r is None or g is None or r['session'] != self.session or r['dispatched'] or g['revoked'] or g['expires'] <= self.clock()
                    or r['binding'] != canonical(asdict(binding)) or r['user'] != permit['user']
                    or permit['expires_at'] != g['expires']
                    or r['grant_id'] != g['id'] or r['version'] != g['version'] or permit['version'] != g['version']):
                raise ValueError('INVALID_OR_REVOKED_GRANT')
            db.execute('UPDATE reservations SET dispatched=1 WHERE id=?', (r['id'],))
            self.audit(db, 'grant_dispatch_authorized', {'reservation': r['id'], 'user': r['user']})
            yield

    def review(self, user, decision_id, feedback_id, reviewer, rationale, preference=None,
               authorization_label=None, consent=False, suitable=False, verified=None):
        if (not reviewer or not rationale or preference not in (None, 'acceptable', 'unwanted')
                or authorization_label not in (None, 'ALLOW', 'ASK', 'BLOCK')
                or type(consent) is not bool or type(suitable) is not bool):
            raise ValueError('INVALID_REVIEW')
        with self.transaction() as db:
            previous = db.execute('SELECT * FROM feedback WHERE id=? OR decision_id=?',
                                  (feedback_id, decision_id)).fetchone()
            data = {'reviewer': reviewer, 'rationale': rationale, 'preference': preference,
                    'authorization_label': authorization_label, 'consent': consent, 'suitable': suitable,
                    'verified': verified}
            if previous:
                if previous['user'] == user and previous['decision_id'] == decision_id and previous['data'] == canonical(data):
                    return False
                raise ValueError('CONFLICTING_FEEDBACK')
            row = db.execute('SELECT data FROM decisions WHERE user=? AND id=?', (user, decision_id)).fetchone()
            if row is None:
                raise ValueError('UNKNOWN_USER_DECISION')
            record = json.loads(row['data'])
            outcome = record.get('outcome')
            if suitable and (not consent or authorization_label is None or outcome is None
                    or outcome.get('error') or outcome.get('terminal') in ('uncertain_execution', 'infrastructure_error')
                    or verified != {'request': True, 'policy': True, 'outcome': True}):
                raise ValueError('REVIEWED_OUTCOME_AND_CONSENT_REQUIRED')
            db.execute('INSERT INTO feedback VALUES(?,?,?,?)', (feedback_id, decision_id, user, canonical(data)))
            if record['mode'] in ('shadow', 'active') and not record['frozen']:
                state = self.state(db, user)
                state['reviewed'] += 1
                if record['action'] == 'USE_EXISTING_GRANT' and outcome and outcome['executed'] and preference:
                    learning.update(state, record['action'], record['features'], 0 if preference == 'acceptable' else 10)
                self.save_state(db, user, state)
            if preference == 'unwanted':
                db.execute('UPDATE grants SET revoked=1,version=version+1 WHERE user=? AND scope=? AND revoked=0',
                           (user, canonical(record['scope'])))
            self.audit(db, 'review', {'user': user, 'decision_id': decision_id, 'feedback_id': feedback_id})
        return True

    def export(self, user):
        with self.transaction() as db:
            rows = db.execute('SELECT f.id,f.data,d.data AS decision FROM feedback f JOIN decisions d '
                              'ON f.decision_id=d.id WHERE f.user=?', (self.user(user),)).fetchall()
            result = []
            for r in rows:
                review, decision = json.loads(r['data']), json.loads(r['decision'])
                if review['consent'] and review['suitable'] and review['authorization_label']:
                    result.append({'feedback_id': r['id'], 'scenario_group': digest(decision['scope']),
                                   'review': review, 'decision': decision, 'provenance': 'explicit_operator_review'})
            return result
