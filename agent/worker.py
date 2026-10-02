import json
import queue
import threading
import time
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

from . import ai, db, discovery, gmail, reports, tailoring
from .browser import BrowserApplicant
from .config import DATA, profile, secret, settings, write_json
from .policy import NeedsReview, coarse_reject, major_company


class Worker:
    def __init__(self):
        self.commands = queue.Queue()
        self.stop = threading.Event()
        self.pause = threading.Event()
        self.state = 'Idle'
        self.thread = None
        self.last_run = 0
        self.last_report_check = 0

    def start(self):
        # One worker owns the persistent browser and queue, including across server processes.
        self.lockfile = (DATA / 'worker.lock').open('a+b')
        self.lockfile.seek(0)
        self.lockfile.write(b'0')
        self.lockfile.flush()
        self.lockfile.seek(0)
        try:
            import msvcrt
            msvcrt.locking(self.lockfile.fileno(), msvcrt.LK_NBLCK, 1)
        except ImportError:
            import fcntl
            fcntl.flock(self.lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
        db.recover()
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        self.pause.set()
        if self.thread:
            self.thread.join(timeout=50)
        self.lockfile.close()

    def enqueue(self, command):
        if command not in ('discover', 'run', 'report'):
            raise ValueError('Unknown command')
        if self.commands.qsize() >= 3:
            raise ValueError('Worker already has pending commands')
        self.commands.put(command)

    def loop(self):
        while not self.stop.is_set():
            try:
                config = settings()
                command = None
                try:
                    command = self.commands.get(timeout=3)
                except queue.Empty:
                    pass
                if command == 'discover':
                    self.state = 'Discovering jobs'
                    discovery.discover(config)
                elif command == 'run' or (config.enabled and time.time() - self.last_run > config.interval_minutes * 60):
                    self.last_run = time.time()
                    self.pause.clear()
                    self.cycle(config)
                if command == 'report' or (config.enabled and secret('GMAIL_TOKEN') and time.time() - self.last_report_check > 300):
                    self.last_report_check = time.time()
                    local = datetime.now(ZoneInfo(config.timezone))
                    if command == 'report' or local.hour >= config.report_hour:
                        self.state = 'Sending daily report'
                        gmail.send_report(local.date().isoformat(), reports.export())
                        db.event('Daily report delivered or already sent')
                self.state = 'Idle'
            except Exception as exc:
                reason = str(exc) if isinstance(exc, NeedsReview) else type(exc).__name__
                db.event('Worker needs attention: ' + reason)
                self.state = 'Needs setup or attention: ' + reason
                self.last_run = time.time()
                self.last_report_check = time.time()

    def cycle(self, config):
        p = profile()
        if not p.get('email') or not any(r.get('enabled') for r in p.get('resumes', {}).values()) or not secret('GEMINI_API_KEY') or not secret('GROQ_API_KEY'):
            raise NeedsReview('Import a profile and configure Gemini and Groq before running applications')
        self.state = 'Discovering jobs'
        discovery.discover(config)
        today = datetime.now(ZoneInfo(config.timezone)).date()
        with db.connection() as c:
            used = sum(1 for row in c.execute('SELECT created FROM attempts') if
                       datetime.fromisoformat(row['created']).astimezone(ZoneInfo(config.timezone)).date() == today)
        evaluated = 0
        for job in reversed(db.jobs('queued')):
            if self.stop.is_set() or self.pause.is_set() or used >= config.daily_limit:
                break
            if not db.claim(job['id']):
                continue
            self.state = f"Evaluating {job['company']} - {job['title']}"
            try:
                if db.possible_duplicate(job) and not job['approved']:
                    raise NeedsReview('A similar role at this company was already submitted or attempted; check for a duplicate')
                reason = coarse_reject(job, p)
                if reason:
                    db.update(job['id'], status='skipped', reason=reason)
                    continue
                if evaluated >= 80:
                    db.update(job['id'], status='queued', reason='Waiting for next evaluation cycle')
                    break
                evaluated += 1
                result = ai.fit(job, p)
                db.update(job['id'], resume=result.resume, score=result.score)
                if not result.relevant or not result.us_eligible or result.sponsorship_excluded:
                    db.update(job['id'], status='skipped', reason=result.reason)
                    continue
                if (major_company(job['company'], config.review_companies) or (config.review_large_tech and result.large_tech_company)) and not job['approved']:
                    raise NeedsReview('Major tech company: your decision is required. ' + result.reason)
                if not p['resumes'].get(result.resume, {}).get('enabled'):
                    raise NeedsReview('Selected resume is not enabled')
                job = db.get(job['id'])
                self.state = f"Applying to {job['company']} - {job['title']}"
                application_profile = tailoring.prepare(job, p) if config.tailor_resumes else p
                resume_path = Path(application_profile['resumes'][job['resume']]['path']).resolve()
                if resume_path.is_relative_to((DATA / 'resumes').resolve()):
                    db.update(job['id'], tailored_resume=str(resume_path.relative_to(DATA)))
                evidence = BrowserApplicant(self.pause).apply(job, application_profile)
                db.update(job['id'], status='applied', reason='Confirmed by application site',
                          applied_at=db.now(), evidence=evidence)
                db.event('Application confirmed', job['id'])
            except ai.ProviderUnavailable as exc:
                current = db.get(job['id'])
                db.update(job['id'], status='needs_review' if current['attempted'] else 'queued', reason=str(exc))
                paused = settings().model_copy(update={'enabled': False})
                write_json(DATA / 'settings.json', paused.model_dump())
                self.pause.set()
                db.event('Automation paused: ' + str(exc), job['id'])
                break
            except NeedsReview as exc:
                db.update(job['id'], status='needs_review', reason=str(exc), questions=json.dumps(exc.questions))
                db.event('Application needs review', job['id'])
            except Exception as exc:
                db.update(job['id'], status='needs_review', reason=f'Execution failed: {type(exc).__name__}; inspect before retrying')
                db.event(f'Application stopped: {type(exc).__name__}', job['id'])
            finally:
                if db.get(job['id'])['attempted']:
                    used += 1
                reports.export()
            self.pause.wait(3)


worker = Worker()
