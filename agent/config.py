import json
import os
import threading
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get('JOB_AGENT_DATA', ROOT / 'data')).resolve()
DATA.mkdir(parents=True, exist_ok=True)
load_dotenv(ROOT / '.env')
LOCK = threading.RLock()


class Settings(BaseModel):
    enabled: bool = False
    interval_minutes: int = Field(default=120, ge=10, le=1440)
    daily_limit: int = Field(default=25, ge=1, le=500)
    report_hour: int = Field(default=18, ge=0, le=23)
    timezone: str = 'America/Los_Angeles'
    model: str = os.environ.get('OPENAI_MODEL', 'gpt-4.1-mini')
    tailor_resumes: bool = True
    interactive_handoff: bool = False
    handoff_timeout_seconds: int = Field(default=180, ge=30, le=900)
    review_large_tech: bool = False
    review_companies: list[str] = Field(default_factory=list)
    sources: list[dict] = Field(default_factory=lambda: [
        {'provider': 'greenhouse', 'board': 'datadog', 'company': 'Datadog'},
        {'provider': 'greenhouse', 'board': 'cloudflare', 'company': 'Cloudflare'},
        {'provider': 'greenhouse', 'board': 'mongodb', 'company': 'MongoDB'},
        {'provider': 'greenhouse', 'board': 'duolingo', 'company': 'Duolingo'},
        {'provider': 'greenhouse', 'board': 'reddit', 'company': 'Reddit'},
        {'provider': 'ashby', 'board': 'ramp', 'company': 'Ramp'},
        {'provider': 'ashby', 'board': 'notion', 'company': 'Notion'},
        {'provider': 'ashby', 'board': 'openai', 'company': 'OpenAI'},
        {'provider': 'greenhouse', 'board': 'anthropic', 'company': 'Anthropic'},
        {'provider': 'greenhouse', 'board': 'stripe', 'company': 'Stripe'}])
    queries: list[str] = Field(default_factory=lambda: [
        'software engineer', 'machine learning engineer', 'data scientist',
        'entry level data engineer', 'entry level IT support', 'junior systems administrator',
        'entry level data analyst', 'junior software developer', 'new graduate software engineer'])


def read_json(path: Path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def write_json(path: Path, value):
    with LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(value, indent=2), encoding='utf-8')
        temp.replace(path)


def settings():
    return Settings.model_validate(read_json(DATA / 'settings.json', {}))


def profile():
    return read_json(DATA / 'profile.json', {})


def secret(name):
    if os.environ.get(name):
        return os.environ[name]
    import keyring
    return keyring.get_password('JobApplicationAgent', name)


def set_secret(name, value):
    import keyring
    keyring.set_password('JobApplicationAgent', name, value)
