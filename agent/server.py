import json
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import db, gmail, reports
from .config import DATA, ROOT, Settings, profile, secret, set_secret, settings, write_json
from .policy import public_url
from .worker import worker


@asynccontextmanager
async def lifespan(app):
    db.init()
    worker.start()
    yield
    worker.close()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver'])


@app.middleware('http')
async def local_only(request: Request, call_next):
    if request.method not in ('GET', 'HEAD'):
        origin = request.headers.get('origin')
        expected = f'{request.url.scheme}://{request.headers.get("host", "")}'
        if (origin and origin != expected) or request.headers.get('x-local-request') != 'job-agent':
            return JSONResponse({'detail': 'Local dashboard requests only'}, status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; connect-src 'self'"
    return response


@app.get('/api/state')
def state():
    with db.connection() as c:
        events = [dict(r) for r in c.execute('SELECT * FROM events ORDER BY id DESC LIMIT 30')]
        delivery = [dict(r) for r in c.execute('SELECT day,status,updated FROM reports ORDER BY day DESC LIMIT 7')]
    p = profile()
    return {'jobs': [{k: v for k, v in j.items() if k != 'description'} for j in db.jobs()], 'events': events, 'worker': worker.state,
            'settings': settings().model_dump(), 'reports': delivery,
            'profile': {k: v for k, v in p.items() if k != 'resumes'},
            'resumes': {k: {'enabled': v.get('enabled'), 'role': v.get('role'), 'placeholder': v.get('placeholder', False),
                           'exists': Path(v['path']).is_file()} for k, v in p.get('resumes', {}).items()},
            'connections': {'gemini': bool(secret('GEMINI_API_KEY')), 'groq': bool(secret('GROQ_API_KEY')), 'gmail': bool(secret('GMAIL_TOKEN')),
                            'gmail_client': (ROOT / 'secrets/gmail-client.json').exists(),
                            'adzuna': bool(secret('ADZUNA_APP_ID') and secret('ADZUNA_APP_KEY'))}}


@app.post('/api/settings')
def change_settings(value: Settings):
    try:
        ZoneInfo(value.timezone)
    except Exception:
        raise HTTPException(422, 'Invalid timezone')
    if value.enabled and not (profile().get('email') and any(r.get('enabled') and Path(r.get('path', '')).is_file() for r in profile().get('resumes', {}).values()) and secret('GEMINI_API_KEY') and secret('GROQ_API_KEY')):
        raise HTTPException(409, 'Save a candidate profile, import an enabled resume, and connect Gemini and Groq before enabling automation')
    write_json(DATA / 'settings.json', value.model_dump())
    if not value.enabled:
        worker.pause.set()
    return {'ok': True}


class KeyInput(BaseModel):
    name: str
    value: str = Field(min_length=1, max_length=5000)


@app.post('/api/credentials')
def credentials(value: KeyInput):
    if value.name not in {'GEMINI_API_KEY', 'GROQ_API_KEY', 'ADZUNA_APP_ID', 'ADZUNA_APP_KEY', 'APIFY_TOKEN'}:
        raise HTTPException(422, 'Unsupported credential')
    set_secret(value.name, value.value.strip())
    return {'ok': True}


class AccountInput(BaseModel):
    site: str
    password: str = Field(min_length=1, max_length=1000)


@app.post('/api/account')
def account(value: AccountInput):
    try:
        public_url(value.site)
    except Exception:
        raise HTTPException(422, 'Enter a public HTTPS site URL')
    host = urlsplit(value.site).hostname
    set_secret(f'ACCOUNT:{host}:{profile()["email"]}', value.password)
    return {'ok': True}


auth_lock = threading.Lock()


@app.post('/api/gmail/connect')
def connect():
    client_file = ROOT / 'secrets/gmail-client.json'
    if not client_file.is_file():
        raise HTTPException(409, 'Place your Google Desktop OAuth client JSON at secrets/gmail-client.json first')
    if not auth_lock.acquire(blocking=False):
        raise HTTPException(409, 'Gmail sign-in is already open')

    def run():
        try:
            gmail.authorize(client_file)
            db.event('Gmail connected')
        except Exception as exc:
            db.event('Gmail sign-in failed: ' + type(exc).__name__)
        finally:
            auth_lock.release()
    threading.Thread(target=run, daemon=True).start()
    return {'ok': True}


@app.post('/api/commands/{command}')
def command(command: str):
    try:
        worker.enqueue(command)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return {'ok': True}


class JobInput(BaseModel):
    company: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=300)
    location: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=30, max_length=60000)
    url: str = Field(max_length=3000)


@app.post('/api/jobs')
def add_job(value: JobInput):
    try:
        public_url(value.url)
    except Exception:
        raise HTTPException(422, 'Job URL must be public HTTPS')
    return {'id': db.add(value.model_dump())}


@app.get('/api/jobs/{jid}')
def job_detail(jid: str):
    job = db.get(jid)
    if not job:
        raise HTTPException(404, 'Job not found')
    return job


class Resolution(BaseModel):
    action: str
    answers: dict[str, str] = Field(default_factory=dict)
    confirm_not_submitted: bool = False
    evidence: str = ''
    remember_answers: bool = False


@app.post('/api/jobs/{jid}/resolve')
def resolve(jid: str, value: Resolution):
    job = db.get(jid)
    if not job:
        raise HTTPException(404, 'Job not found')
    if job['status'] not in ('needs_review', 'skipped'):
        raise HTTPException(409, 'Only stopped applications can be resolved')
    if value.action == 'skip':
        db.update(jid, status='skipped', reason='Skipped by user')
    elif value.action == 'applied':
        if not value.evidence.strip():
            raise HTTPException(422, 'Record how you confirmed submission')
        db.update(jid, status='applied', reason='User confirmed: ' + value.evidence,
                  applied_at=db.now(), attempted=1)
    elif value.action == 'retry':
        if job['attempted'] and not value.confirm_not_submitted:
            raise HTTPException(409, 'Check the employer site and confirm no application was submitted before retrying')
        for question, answer in value.answers.items():
            if answer.strip():
                db.save_answer(jid, question, answer.strip())
        if value.remember_answers:
            p = profile()
            p.setdefault('answers', {}).update({q:a.strip() for q,a in value.answers.items() if a.strip()})
            write_json(DATA / 'profile.json', p)
        db.update(jid, status='queued', approved=1, attempted=0, reason='Approved by user', questions='[]')
    else:
        raise HTTPException(422, 'Unknown resolution')
    db.event('User resolved application: ' + value.action, jid)
    return {'ok': True}


@app.get('/api/export')
def export():
    path = reports.export()
    return FileResponse(path, filename=path.name)


@app.get('/api/evidence/{jid}')
def evidence(jid: str):
    job = db.get(jid)
    if not job or not job['evidence']:
        raise HTTPException(404, 'No saved screenshot')
    path = (DATA / job['evidence']).resolve()
    if not path.is_relative_to((DATA / 'evidence').resolve()) or not path.is_file():
        raise HTTPException(404, 'Evidence unavailable')
    return FileResponse(path)


@app.get('/api/resumes/{jid}')
def application_resume(jid: str):
    job = db.get(jid)
    if not job or not job['tailored_resume']:
        raise HTTPException(404, 'No prepared resume')
    path = (DATA / job['tailored_resume']).resolve()
    if not path.is_relative_to((DATA / 'resumes').resolve()) or not path.is_file():
        raise HTTPException(404, 'Resume unavailable')
    return FileResponse(path, filename=f'resume-{jid}.pdf')


class MFAInput(BaseModel):
    site: str
    seed: str = Field(min_length=16, max_length=256)


@app.post('/api/mfa')
def configure_mfa(value: MFAInput):
    from .mfa import totp
    try:
        public_url(value.site)
        totp(value.seed)
    except Exception:
        raise HTTPException(422, 'Enter a public HTTPS career site and valid Base32 authenticator seed')
    email = profile().get('email')
    if not email:
        raise HTTPException(409, 'Save your candidate email first')
    set_secret(f'TOTP:{urlsplit(value.site).hostname}:{email}', ''.join(value.seed.split()).upper())
    return {'ok': True}


class CandidateInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    first_name: str = ''
    last_name: str = ''
    email: str = Field(min_length=3, max_length=254)
    phone: str = ''
    location: str = ''
    city: str = ''
    country: str = ''
    linkedin: str = ''
    github: str = ''
    work_authorization: str = ''
    authorized_to_work_us: bool | None = None
    requires_sponsorship: bool | None = None
    willing_to_relocate: bool | None = None
    preferences: str = 'Entry-level technical roles in the United States'
    answers: dict[str, str] = Field(default_factory=dict)


@app.post('/api/profile')
def save_profile(value: CandidateInput):
    if '@' not in value.email or any(c.isspace() for c in value.email):
        raise HTTPException(422, 'Enter a valid email address')
    p = value.model_dump()
    p['resumes'] = profile().get('resumes', {})
    write_json(DATA / 'profile.json', p)
    return {'ok': True}


class ResumeInput(BaseModel):
    kind: str
    content: str = Field(min_length=1, max_length=14_000_000)


@app.post('/api/resumes')
def import_resume(value: ResumeInput):
    import base64
    import io
    from pypdf import PdfReader
    roles = {'sde': 'Software Engineering', 'aiml': 'AI and Machine Learning',
             'ds': 'Data Science', 'it': 'IT and Cloud Infrastructure'}
    if value.kind not in roles:
        raise HTTPException(422, 'Unknown resume slot')
    try:
        content = base64.b64decode(value.content, validate=True)
        if not content.startswith(b'%PDF-') or len(content) > 10_000_000:
            raise ValueError()
        reader = PdfReader(io.BytesIO(content))
        if len(reader.pages) > 20:
            raise ValueError()
        text = '\n'.join(page.extract_text() or '' for page in reader.pages)
        if len(text.strip()) < 50:
            raise ValueError()
    except Exception:
        raise HTTPException(422, 'Upload a readable PDF under 10 MB and 20 pages; scanned PDFs need OCR first')
    folder = DATA / 'resumes'
    folder.mkdir(exist_ok=True)
    path = folder / f'{value.kind}.pdf'
    temporary = path.with_suffix('.tmp')
    temporary.write_bytes(content)
    temporary.replace(path)
    p = profile()
    p.setdefault('resumes', {})[value.kind] = {'path': str(path.resolve()), 'text': text,
        'enabled': True, 'role': roles[value.kind]}
    write_json(DATA / 'profile.json', p)
    return {'ok': True}


app.mount('/', StaticFiles(directory=ROOT / 'static', html=True), name='dashboard')
