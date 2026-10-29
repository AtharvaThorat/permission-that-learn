"""Local-filesystem run index. SQLite serializes short claim/publication transactions.

One coordinator connection is protected by a mutex. Separate local coordinators
use SQLite transactions; network/shared cluster filesystems are not supported.
"""
import json
from pathlib import Path
import sqlite3
import threading
import time
from uuid import uuid4
from .artifacts import atomic, now, Result
from .spec import plan


def create_run(spec, output):
    resolved = plan(spec)
    directory = Path(output) / (spec.name[:24] + '-' + uuid4().hex[:16])
    directory.mkdir(parents=True, exist_ok=False)
    atomic(directory / 'spec.json', spec.model_dump(mode='json'))
    atomic(directory / 'plan.json', resolved)
    atomic(directory / 'manifest.json', {'schema_version': 1, 'run_id': directory.name,
        'created_at': now(), 'spec_id': resolved['spec_id'], 'implementation': resolved['identity']['implementation'],
        'storage': 'local_filesystem_sqlite', 'specification': 'spec.json', 'plan': 'plan.json',
        'credentials': 'environment values are never saved', 'mid_episode_resume': False})
    return directory


def compatible(directory, spec):
    recorded = json.loads((Path(directory) / 'plan.json').read_text(encoding='utf-8'))
    current = plan(spec)
    if recorded['spec_id'] != current['spec_id'] or recorded['identity'] != current['identity']:
        raise ValueError('Incompatible configuration/source; create a new experiment run')
    return recorded


class Index:
    def __init__(self, directory, lease_seconds=120):
        self.directory = Path(directory)
        self.owner = uuid4().hex
        self.lease_seconds = lease_seconds
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.directory / 'index.sqlite', timeout=30, check_same_thread=False,
                                  isolation_level=None)
        self.db.execute('PRAGMA journal_mode=DELETE')
        self.db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, attempt TEXT, owner TEXT, expires REAL, status TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS attempts (sequence INTEGER PRIMARY KEY AUTOINCREMENT, job TEXT, attempt TEXT UNIQUE, status TEXT, relative_path TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS coordinator (id INTEGER PRIMARY KEY, owner TEXT, expires REAL)')

    def coordinate(self):
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            row = self.db.execute('SELECT owner,expires FROM coordinator WHERE id=1').fetchone()
            if row and row[1] > time.time() and row[0] != self.owner:
                self.db.execute('ROLLBACK')
                raise RuntimeError('Another coordinator holds this run')
            self.db.execute('INSERT OR REPLACE INTO coordinator VALUES (1,?,?)',
                            (self.owner, time.time()+self.lease_seconds))
            self.db.execute('COMMIT')

    def claim(self, job, retry_statuses=()):
        key = job['episode_spec_id']
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                row = self.db.execute('SELECT attempt,owner,expires,status FROM jobs WHERE id=?', (key,)).fetchone()
                if row:
                    published = self.directory / 'episodes' / key[:16] / row[0] / 'result.json'
                    if row[3] == 'active' and published.exists():
                        recovered = Result.model_validate_json(published.read_text(encoding='utf-8'))
                        if recovered.episode_spec_id != key or recovered.attempt_id != row[0]:
                            raise ValueError('Recovery identity conflict')
                        self.db.execute('UPDATE jobs SET status=? WHERE id=?', (recovered.lifecycle,key))
                        self.db.execute('UPDATE attempts SET status=? WHERE attempt=?', (recovered.lifecycle,row[0]))
                        row = (*row[:3], recovered.lifecycle)
                    if row[3] == 'active' and row[2] > time.time():
                        self.db.execute('COMMIT')
                        return None
                    if row[3] != 'active' and row[3] not in retry_statuses:
                        self.db.execute('COMMIT')
                        return None
                    if row[3] == 'active':
                        self.db.execute("UPDATE attempts SET status='interrupted' WHERE attempt=?", (row[0],))
                attempt = uuid4().hex
                relative = f'episodes/{key[:16]}/{attempt}'
                self.db.execute('INSERT OR REPLACE INTO jobs VALUES (?,?,?,?,?)',
                                (key, attempt, self.owner, time.time() + self.lease_seconds, 'active'))
                self.db.execute('INSERT INTO attempts(job,attempt,status,relative_path) VALUES (?,?,?,?)',
                                (key, attempt, 'active', relative))
                directory = self.directory / relative
                directory.mkdir(parents=True, exist_ok=False)
                atomic(directory / 'manifest.json', {'schema_version': 1, 'attempt_id': attempt,
                      'run_id': self.directory.name, 'job': job, 'started_at': now(), 'state': 'incomplete'})
                self.db.execute('COMMIT')
                return attempt, directory
            except BaseException:
                self.db.execute('ROLLBACK')
                raise

    def heartbeat(self):
        with self.lock:
            self.db.execute('UPDATE coordinator SET expires=? WHERE owner=?',
                            (time.time()+self.lease_seconds, self.owner))
            self.db.execute("UPDATE jobs SET expires=? WHERE owner=? AND status='active'",
                            (time.time() + self.lease_seconds, self.owner))

    def publish(self, job, attempt, result):
        result = Result.model_validate(result).model_dump(mode='json')
        if result['episode_spec_id'] != job['episode_spec_id'] or result['attempt_id'] != attempt:
            raise ValueError('Result identity mismatch')
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                row = self.db.execute('SELECT attempt,owner,expires,status FROM jobs WHERE id=?',
                                      (job['episode_spec_id'],)).fetchone()
                if not row or row[:2] != (attempt, self.owner) or row[2] < time.time() or row[3] != 'active':
                    raise RuntimeError('Lease lost: cannot publish')
                path = self.directory / 'episodes' / job['episode_spec_id'][:16] / attempt / 'result.json'
                if path.exists():
                    raise RuntimeError('Attempt already published')
                atomic(path, result)
                self.db.execute('UPDATE jobs SET status=? WHERE id=?', (result['lifecycle'], job['episode_spec_id']))
                self.db.execute('UPDATE attempts SET status=? WHERE attempt=?', (result['lifecycle'], attempt))
                self.db.execute('COMMIT')
            except BaseException:
                self.db.execute('ROLLBACK')
                raise

    def snapshot(self):
        with self.lock:
            rows = self.db.execute('SELECT sequence,job,attempt,status,relative_path FROM attempts ORDER BY sequence').fetchall()
        return [dict(zip(('sequence','episode_spec_id','attempt_id','status','path'), row)) for row in rows]

    def fail(self, job, attempt, error):
        """Record an unexpected worker/publication failure without replacing results."""
        key = job['episode_spec_id']
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                row = self.db.execute('SELECT attempt,owner,expires,status FROM jobs WHERE id=?', (key,)).fetchone()
                if not row or row[:2] != (attempt, self.owner) or row[2] < time.time() or row[3] != 'active':
                    raise RuntimeError('Lease lost: cannot record failure')
                directory = self.directory / 'episodes' / key[:16] / attempt
                if (directory / 'result.json').exists():
                    raise RuntimeError('Result already exists; recover publication on resume')
                atomic(directory / 'failure.json', {'lifecycle': 'infrastructure_error',
                       'error_kind': type(error).__name__, 'ended_at': now()})
                self.db.execute("UPDATE jobs SET status='infrastructure_error' WHERE id=?", (key,))
                self.db.execute("UPDATE attempts SET status='infrastructure_error' WHERE attempt=?", (attempt,))
                self.db.execute('COMMIT')
            except BaseException:
                self.db.execute('ROLLBACK')
                raise

    def close(self):
        self.db.execute('DELETE FROM coordinator WHERE owner=?', (self.owner,))
        self.db.close()
