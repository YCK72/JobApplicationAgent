import base64
import json
import re
import time
from email.message import EmailMessage
from email.utils import getaddresses
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from . import db
from .config import DATA, profile, secret, set_secret
from .discovery import plain
from .policy import NeedsReview, normalized

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/gmail.send']


def service():
    saved = secret('GMAIL_TOKEN')
    if not saved:
        raise NeedsReview('Connect Gmail in Settings before automatic verification or reports')
    credentials = Credentials.from_authorized_user_info(json.loads(saved), SCOPES)
    if not credentials.valid:
        if not credentials.refresh_token:
            raise NeedsReview('Reconnect Gmail: the authorization has expired')
        credentials.refresh(Request())
        set_secret('GMAIL_TOKEN', credentials.to_json())
    api = build('gmail', 'v1', credentials=credentials, cache_discovery=False)
    identity = api.users().getProfile(userId='me').execute()['emailAddress']
    if identity.casefold() != profile().get('email', '').casefold():
        raise NeedsReview('Connected Gmail account differs from the application email')
    return api


def authorize(client_file):
    flow = InstalledAppFlow.from_client_secrets_file(str(client_file), SCOPES)
    credentials = flow.run_local_server(port=0, access_type='offline', prompt='consent', timeout_seconds=300)
    api = build('gmail', 'v1', credentials=credentials, cache_discovery=False)
    identity = api.users().getProfile(userId='me').execute()['emailAddress']
    if identity.casefold() != profile().get('email', '').casefold():
        raise ValueError('Authorize the same Gmail address as your profile')
    set_secret('GMAIL_TOKEN', credentials.to_json())
    return identity


def message_text(payload):
    chunks = []
    if payload.get('mimeType') in ('text/plain', 'text/html'):
        data = payload.get('body', {}).get('data', '')
        if data:
            chunks.append(plain(base64.urlsafe_b64decode(data + '=' * (-len(data) % 4)).decode('utf-8', 'replace')))
    for part in payload.get('parts', []):
        chunks.append(message_text(part))
    return ' '.join(chunks)


def extract_code(message, *, recipient, sender_domains, company, since):
    if int(message.get('internalDate', 0)) / 1000 < since:
        return None
    headers = {h['name'].lower(): h['value'] for h in message['payload'].get('headers', [])}
    recipients = [a.casefold() for _, a in getaddresses([headers.get('to', ''), headers.get('delivered-to', '')])]
    senders = getaddresses([headers.get('from', '')])
    if recipient.casefold() not in recipients or len(senders) != 1:
        return None
    domain = senders[0][1].rsplit('@', 1)[-1].lower()
    if not any(domain == d or domain.endswith('.' + d) for d in sender_domains):
        return None
    auth = headers.get('authentication-results', '').lower()
    aligned = re.findall(r'(?:^|;)\s*(?:dkim|dmarc)=pass\b[^;]*?header\.(?:d|from)=([a-z0-9.-]+)', auth)
    if not any(domain == d or domain.endswith('.' + d) for d in aligned):
        return None
    text = headers.get('subject', '') + ' ' + message_text(message['payload'])
    if normalized(company) not in normalized(text):
        return None
    codes = set(re.findall(r'(?:verification|security|one.time|confirmation|authentication)\s+code\s*(?:is|:)??\s*[:\-]?\s*(\d{4,8})\b', text, re.I))
    return next(iter(codes)) if len(codes) == 1 else None


def verification_code(job, domains, since, stop_event, timeout=90):
    api = service()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not stop_event.is_set():
        result = api.users().messages().list(userId='me', q=f'after:{int(since)} to:{profile()["email"]}', maxResults=25).execute()
        candidates = []
        for item in result.get('messages', []):
            with db.connection() as c:
                if c.execute('SELECT 1 FROM used_codes WHERE message_id=?', (item['id'],)).fetchone():
                    continue
            msg = api.users().messages().get(userId='me', id=item['id'], format='full').execute()
            code = extract_code(msg, recipient=profile()['email'], sender_domains=domains,
                                company=job['company'], since=since)
            if code:
                candidates.append((item['id'], code))
        if len(candidates) > 1:
            raise NeedsReview('Multiple verification emails match this application')
        if candidates:
            mid, code = candidates[0]
            with db.connection() as c:
                c.execute('INSERT INTO used_codes VALUES(?,?,?)', (mid, job['id'], db.now()))
            return code
        stop_event.wait(5)
    raise NeedsReview('Verification code not found in a recent authenticated email for this company')


def send_report(day, workbook):
    api = service()
    message_id = f'<job-agent-{day}@local.jobapplicationagent>'
    with db.connection() as c:
        row = c.execute('SELECT * FROM reports WHERE day=?', (day,)).fetchone()
        if row and row['status'] == 'sent':
            return 'already_sent'
        if row and row['status'] == 'sending':
            existing = api.users().messages().list(userId='me', q=f'in:sent rfc822msgid:{message_id}').execute()
            if existing.get('messages'):
                c.execute("UPDATE reports SET status='sent',message_id=?,updated=? WHERE day=?",
                          (existing['messages'][0]['id'], db.now(), day))
                return 'reconciled'
            raise NeedsReview('Previous report delivery is uncertain; check Sent mail before retrying')
    msg = EmailMessage()
    msg['To'] = profile()['email']
    msg['From'] = profile()['email']
    msg['Subject'] = f'Job applications - {day}'
    msg['Message-ID'] = message_id
    rows = db.jobs()
    applied = sum(j['status'] == 'applied' for j in rows)
    review = sum(j['status'] == 'needs_review' for j in rows)
    msg.set_content(f'Application tracker attached.\n\nConfirmed applied: {applied}\nNeeds review: {review}\n\nOpen your local Job Application Agent dashboard to resolve decisions.\n')
    msg.add_attachment(Path(workbook).read_bytes(), maintype='application',
        subtype='vnd.openxmlformats-officedocument.spreadsheetml.sheet', filename=Path(workbook).name)
    with db.connection() as c:
        c.execute('INSERT OR REPLACE INTO reports VALUES(?,?,?,?)', (day, 'sending', None, db.now()))
    sent = api.users().messages().send(userId='me', body={'raw': base64.urlsafe_b64encode(msg.as_bytes()).decode()}).execute()
    with db.connection() as c:
        c.execute("UPDATE reports SET status='sent',message_id=?,updated=? WHERE day=?", (sent['id'], db.now(), day))
    return 'sent'
