"""Lets the existing app code (written for SQLite) run on Neon Postgres.

Usage in app.py: replace `import sqlite3` with `from pgcompat import sqlite3`.
Needs the DATABASE_URL environment variable and `psycopg2-binary` in requirements.txt.
"""
import os
import re
import datetime

import psycopg2


class _Row(tuple):
    """A row you can read by position (row[0]) or by column name (row['phone'])."""
    def __new__(cls, values, names):
        obj = super().__new__(cls, values)
        obj._names = names
        return obj

    def __getitem__(self, key):
        if isinstance(key, str):
            return tuple.__getitem__(self, self._names.index(key))
        return tuple.__getitem__(self, key)

    def keys(self):
        return list(self._names)


def _plain(value):
    # SQLite gave dates back as text; keep doing that so the pages behave the same
    if isinstance(value, datetime.datetime):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    return value


def _sql(query):
    q = query.strip()

    m = re.match(r'PRAGMA table_info\((\w+)\)', q, re.I)
    if m:
        return ("SELECT ordinal_position - 1, column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = '" + m.group(1) + "' "
                "ORDER BY ordinal_position")

    q = re.sub(r'INTEGER PRIMARY KEY AUTOINCREMENT', 'SERIAL PRIMARY KEY', q, flags=re.I)
    q = re.sub(r'\bREAL\b', 'DOUBLE PRECISION', q)
    q = q.replace('TEXT DEFAULT CURRENT_TIMESTAMP', 'TEXT DEFAULT (now()::text)')
    q = re.sub(r'ADD COLUMN (?!IF NOT EXISTS)', 'ADD COLUMN IF NOT EXISTS ', q, flags=re.I)

    q = re.sub(
        r'INSERT OR REPLACE INTO otps \(phone, code_hash, expires, attempts, sent_at\) VALUES \(([^)]*)\)',
        r'INSERT INTO otps (phone, code_hash, expires, attempts, sent_at) VALUES (\1) '
        r'ON CONFLICT (phone) DO UPDATE SET code_hash = EXCLUDED.code_hash, '
        r'expires = EXCLUDED.expires, attempts = EXCLUDED.attempts, sent_at = EXCLUDED.sent_at',
        q, flags=re.I)

    if re.match(r'INSERT OR IGNORE INTO', q, re.I):
        q = re.sub(r'INSERT OR IGNORE INTO', 'INSERT INTO', q, count=1, flags=re.I) + ' ON CONFLICT DO NOTHING'

    return q.replace('?', '%s')


class _Cursor:
    def __init__(self, cur):
        self._cur = cur

    def execute(self, query, params=()):
        self._cur.execute(_sql(query), tuple(params) if params else None)
        return self

    def _wrap(self, row):
        names = [d[0] for d in self._cur.description]
        return _Row([_plain(v) for v in row], names)

    def fetchone(self):
        row = self._cur.fetchone()
        return self._wrap(row) if row else None

    def fetchall(self):
        return [self._wrap(r) for r in self._cur.fetchall()]

    @property
    def rowcount(self):
        return self._cur.rowcount


class _Connection:
    row_factory = None  # app.py sets this; Postgres rows already work by name

    def __init__(self):
        url = os.environ.get('DATABASE_URL')
        if not url:
            raise RuntimeError('DATABASE_URL is not set. Add it in Render, under Environment.')
        self._conn = psycopg2.connect(url)

    def cursor(self):
        return _Cursor(self._conn.cursor())

    def execute(self, query, params=()):
        return self.cursor().execute(query, params)

    def executescript(self, script):
        cur = self._conn.cursor()
        for statement in script.split(';'):
            if statement.strip():
                cur.execute(_sql(statement))

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


class sqlite3:  # stands in for the sqlite3 module in app.py
    Row = None

    @staticmethod
    def connect(_ignored=None):
        return _Connection()
