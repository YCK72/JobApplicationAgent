import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from .config import DATA


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(url):
    p = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(p.query) if not k.startswith('utm_') and k not in {'source', 'ref', 'referrer'}]
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip('/'), urlencode(sorted(query)), ''))


@contextmanager
def connection():
    con = sqlite3.connect(DATA / 'jobs.sqlite3', timeout=30)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()


def init():
    with connection() as c:
        c.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY, url TEXT UNIQUE NOT NULL, company TEXT NOT NULL,
          title TEXT NOT NULL, location TEXT NOT NULL, description TEXT NOT NULL,
          source TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued',
          reason TEXT NOT NULL DEFAULT '', resume TEXT NOT NULL DEFAULT '',
          score INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL, updated TEXT NOT NULL,
          applied_at TEXT, evidence TEXT NOT NULL DEFAULT '', approved INTEGER NOT NULL DEFAULT 0,
          attempted INTEGER NOT NULL DEFAULT 0, questions TEXT NOT NULL DEFAULT '[]');
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY, created TEXT NOT NULL, job_id TEXT, message TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS answers (
          job_id TEXT NOT NULL, question TEXT NOT NULL, answer TEXT NOT NULL,
          PRIMARY KEY(job_id, question));
        CREATE TABLE IF NOT EXISTS reports (
          day TEXT PRIMARY KEY, status TEXT NOT NULL, message_id TEXT, updated TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS used_codes (
          message_id TEXT PRIMARY KEY, job_id TEXT NOT NULL, used_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS attempts (
          id INTEGER PRIMARY KEY, job_id TEXT NOT NULL, created TEXT NOT NULL);
        ''')
        columns = {r['name'] for r in c.execute('PRAGMA table_info(jobs)')}
        if 'tailored_resume' not in columns:
            c.execute("ALTER TABLE jobs ADD COLUMN tailored_resume TEXT NOT NULL DEFAULT ''")


def event(message, job_id=None):
    with connection() as c:
        c.execute('INSERT INTO events(created,job_id,message) VALUES(?,?,?)', (now(), job_id, message))


def add(job):
    url = canonical(job['url'])
    jid = hashlib.sha256(url.encode()).hexdigest()[:20]
    with connection() as c:
        c.execute('''INSERT OR IGNORE INTO jobs
          (id,url,company,title,location,description,source,created,updated)
          VALUES(?,?,?,?,?,?,?,?,?)''', (jid, url, job['company'], job['title'], job.get('location', ''),
            job.get('description', ''), job.get('source', 'manual'), now(), now()))
        return c.execute('SELECT id FROM jobs WHERE url=?', (url,)).fetchone()['id']


def jobs(status=None):
    with connection() as c:
        rows = c.execute('SELECT * FROM jobs' + (' WHERE status=?' if status else '') +
                         ' ORDER BY updated DESC', (status,) if status else ()).fetchall()
    return [dict(r) for r in rows]


def get(jid):
    with connection() as c:
        row = c.execute('SELECT * FROM jobs WHERE id=?', (jid,)).fetchone()
    return dict(row) if row else None


def update(jid, **values):
    allowed = {'status', 'reason', 'resume', 'score', 'applied_at', 'evidence', 'approved', 'attempted', 'questions', 'tailored_resume'}
    if not values or not set(values) <= allowed:
        raise ValueError('Invalid job update')
    values['updated'] = now()
    with connection() as c:
        if values.get('attempted') == 1:
            previous = c.execute('SELECT attempted FROM jobs WHERE id=?', (jid,)).fetchone()
            if previous and not previous['attempted']:
                c.execute('INSERT INTO attempts(job_id,created) VALUES(?,?)', (jid, now()))
        c.execute('UPDATE jobs SET ' + ','.join(f'{k}=?' for k in values) + ' WHERE id=?', (*values.values(), jid))


def possible_duplicate(job):
    from .policy import normalized
    for other in jobs():
        if other['id'] != job['id'] and (other['status'] == 'applied' or other['attempted']):
            if normalized(other['company']) == normalized(job['company']) and normalized(other['title']) == normalized(job['title']):
                return other
    return None


def claim(jid):
    with connection() as c:
        return c.execute("UPDATE jobs SET status='running',updated=? WHERE id=? AND status='queued' AND attempted=0",
                         (now(), jid)).rowcount == 1


def recover():
    with connection() as c:
        c.execute("UPDATE jobs SET status='needs_review',reason='Worker stopped; inspect saved evidence before retrying.',updated=? WHERE status='running'", (now(),))


def answers(jid):
    with connection() as c:
        return dict(c.execute('SELECT question,answer FROM answers WHERE job_id=?', (jid,)).fetchall())


def save_answer(jid, question, answer):
    with connection() as c:
        c.execute('INSERT OR REPLACE INTO answers VALUES(?,?,?)', (jid, question, answer))
