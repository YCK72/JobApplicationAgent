import hashlib
import json
import re
import secrets
import time
from pathlib import Path
from urllib.parse import urlsplit, urljoin

from playwright.sync_api import sync_playwright

from . import ai, db, gmail, mfa
from .config import DATA, secret, set_secret, settings
from .policy import DECISION, NeedsReview, public_url

SCAN = r'''() => {
 const visible = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
 const label = e => {
   const radioGroup = e.closest('[role="radiogroup"]');
   const group = e.closest('fieldset')?.querySelector('legend')?.innerText || radioGroup?.getAttribute('aria-label') ||
     (radioGroup?.getAttribute('aria-labelledby') || '').split(' ').map(id=>document.getElementById(id)?.innerText||'').join(' ');
   const own = [...(e.labels || [])].map(l => {const copy=l.cloneNode(true);
     copy.querySelectorAll('input,textarea,select,button,[role="combobox"],[contenteditable]').forEach(n=>n.remove());
     return copy.textContent.trim();}).join(' ');
   const aria = (e.getAttribute('aria-labelledby') || '').split(' ').map(id => document.getElementById(id)?.innerText || '').join(' ');
   return ((e.type === 'radio' || e.getAttribute('role') === 'radio') && group ? group : own || e.getAttribute('aria-label') || aria || e.getAttribute('placeholder') || e.name || '').trim();
 };
 const fields = [...document.querySelectorAll('input,textarea,select,[role="combobox"],[role="textbox"][contenteditable="true"],[role="checkbox"],[role="radio"]')]
  .filter(e => (visible(e) || e.type === 'file') && !e.disabled && e.type !== 'hidden' && !['submit','button','reset'].includes(e.type))
  .map((e,i) => {
   e.setAttribute('data-agent-field', String(i));
   return {id:i, label:label(e), type:e.type || e.getAttribute('role'), tag:e.tagName.toLowerCase(),
    name:e.name || '', value:e.type === 'password' ? '' : e.value || '', checked:!!e.checked || e.getAttribute('aria-checked') === 'true',
    multiple:!!e.multiple,
    required:!!e.required || e.getAttribute('aria-required') === 'true' || label(e).includes('*'),
    options:e.tagName === 'SELECT' ? [...e.options].filter(o=>!o.disabled && o.value).map(o=>o.textContent.trim()) : [],
    option:(e.type === 'radio' || e.getAttribute('role') === 'radio') ? ([...(e.labels||[])].map(l=>l.innerText).join(' ') || e.getAttribute('aria-label') || e.innerText || '').trim() : '',
    autocomplete:e.autocomplete || ''};
  });
 const buttons=[...document.querySelectorAll('button,a,input[type="submit"],[role="button"]')]
  .filter(e=>visible(e) && !e.disabled).map((e,i)=>{
   e.setAttribute('data-agent-button',String(i));
   return {id:i,text:(e.innerText || e.value || e.getAttribute('aria-label') || '').trim(),href:e.href || ''};
  });
 return {fields,buttons,text:document.body.innerText.slice(0,40000)};
}'''

SUCCESS = re.compile(r'your application (?:has been |was )?(?:successfully )?(?:submitted|received)|'
    r'thank you for applying|thanks for applying|application submitted successfully', re.I)
SUBMIT = re.compile(r'^(?:submit(?: my| your)? application|send application|submit|apply now)$', re.I)
NEXT = re.compile(r'^(?:next|continue|save (?:and|&) continue|review(?: application)?|verify|verify (?:email|code)|confirm code)$', re.I)
ENTER = re.compile(r'^(?:apply(?: for this job| now| on company site)?|easy apply|apply manually|apply with resume|start application|create (?:an )?account|sign up|sign in|log in)$', re.I)
OTP = re.compile(r'verification code|security code|one.time (?:code|password)|confirmation code|authentication code|authenticator code|two.factor code', re.I)
SECURITY = re.compile(r'verify you are human|complete the captcha|i.?m not a robot|i am human|unusual traffic|access denied|security check|approve (?:the |this )?(?:sign.?in|login)|push notification|code sent to (?:your )?phone', re.I)


def platform(host):
    if host.endswith(('.myworkdayjobs.com', '.myworkdaysite.com')):
        return 'workday', ['myworkday.com', 'workday.com']
    for name, suffix in [('greenhouse', 'greenhouse.io'), ('lever', 'lever.co'), ('ashby', 'ashbyhq.com')]:
        if host == suffix or host.endswith('.' + suffix):
            return name, [suffix]
    return 'generic', [host.removeprefix('www.')]


def save_evidence(page, job, suffix):
    folder = DATA / 'evidence' / job['id']
    folder.mkdir(parents=True, exist_ok=True)
    filename = folder / f'{int(time.time())}-{suffix}.png'
    page.screenshot(path=str(filename), full_page=True)
    return str(filename.relative_to(DATA))


def verification_response(route, host):
    """Inspect every HTTP redirect before sending the next verification request."""
    current = route.request.url
    for _ in range(6):
        target = urlsplit(current)
        if target.scheme != 'https' or target.hostname != host or target.username or target.password or target.port not in (None,443):
            raise NeedsReview('Verification navigation changed career-site host or protocol')
        public_url(current)
        response = route.fetch(url=current, max_redirects=0, timeout=15000)
        if response.status not in (301,302,303,307,308):
            return response
        location = response.headers.get('location')
        if not location:
            raise NeedsReview('Verification redirect has no destination')
        current = urljoin(current, location)
    raise NeedsReview('Verification link exceeded the redirect limit')


class BrowserApplicant:
    def __init__(self, stop_event):
        self.stop_event = stop_event

    def apply(self, job, profile):
        public_url(job['url'])
        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(
                str(DATA / 'browser'), headless=not settings().interactive_handoff, accept_downloads=False,
                service_workers='block', viewport={'width': 1440, 'height': 1000})
            checked_hosts = set()

            def guard(route):
                url = route.request.url
                if url.startswith(('data:', 'blob:')):
                    return route.continue_()
                try:
                    host = urlsplit(url).netloc
                    if host not in checked_hosts:
                        public_url(url)
                        checked_hosts.add(host)
                    route.continue_()
                except Exception:
                    route.abort()

            context.route('**/*', guard)
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(12000)
            try:
                response = page.goto(job['url'], wait_until='domcontentloaded', timeout=45000)
                if response and response.status == 429:
                    try:
                        delay = int(response.headers.get('retry-after', '30'))
                    except ValueError:
                        delay = 30
                    if not 1 <= delay <= 60:
                        raise NeedsReview('Site rate limit requires a longer wait; retry later')
                    db.event('Career site requested a rate-limit delay; waiting before one retry', job['id'])
                    if self.stop_event.wait(delay):
                        raise NeedsReview('Automation paused during rate-limit wait')
                    response = page.goto(job['url'], wait_until='domcontentloaded', timeout=45000)
                    if response and response.status == 429:
                        raise NeedsReview('Career site remains rate-limited; retry later')
                return self.run(page, job, profile)
            except NeedsReview as exc:
                try:
                    db.update(job['id'], evidence=save_evidence(page, job, 'review'))
                except Exception:
                    pass
                raise exc
            finally:
                context.close()

    def security_handoff(self, page, job, challenge=SECURITY):
        config = settings()
        if not config.interactive_handoff:
            raise NeedsReview('Interactive authentication required; enable browser handoff in Settings and retry after checking submission status')
        db.event('Complete the security or MFA prompt in the application browser; automation will resume when it clears', job['id'])
        deadline = time.monotonic() + config.handoff_timeout_seconds
        while time.monotonic() < deadline and not self.stop_event.is_set():
            page.wait_for_timeout(1000)
            text = '\n'.join(f.locator('body').inner_text() for f in page.frames)
            if not challenge.search(text):
                return
        raise NeedsReview('Browser handoff timed out or was paused; inspect the application before retrying')

    def follow_verification_link(self, page, job, started):
        host = urlsplit(page.url).hostname
        _, domains = platform(host)
        link = gmail.verification_link(job, domains, [host], started, self.stop_event)
        public_url(link)
        blocked = []
        def guard(route):
            if route.request.is_navigation_request() and route.request.frame == page.main_frame:
                try:
                    response = verification_response(route, host)
                    route.fulfill(response=response)
                except Exception:
                    blocked.append(True)
                    route.abort()
            else:
                route.fallback()
        page.route('**/*', guard)
        try:
            try:
                page.goto(link, wait_until='domcontentloaded', timeout=45000)
            except Exception:
                if blocked:
                    raise NeedsReview('Verification navigation was blocked or failed; inspect the career site')
                raise
            if urlsplit(page.url).hostname != host:
                raise NeedsReview('Verification navigation changed career-site host')
        finally:
            page.unroute('**/*', guard)

    def verification_code(self, job, profile, host, label, text, started):
        if re.search(r'authenticator|authentication app|two.factor app', label + ' ' + text, re.I):
            return mfa.account_code(host, profile['email'])
        _, domains = platform(host)
        return gmail.verification_code(job, domains, started, self.stop_event)

    def run(self, page, job, profile):
        overrides = {**profile.get('answers', {}), **db.answers(job['id'])}
        started = time.time()
        submitted = False
        account_sent = False
        resume_uploaded = False
        last_signature = ''
        repeated = 0
        link_followed = False
        for step in range(24):
            if self.stop_event.is_set():
                raise NeedsReview('Automation paused')
            public_url(page.url)
            page.wait_for_timeout(800)
            snapshots = []
            for frame in page.frames:
                try:
                    state = frame.evaluate(SCAN)
                    snapshots.append((frame, state))
                except Exception:
                    continue
            text = '\n'.join(s['text'] for _, s in snapshots)
            if submitted and SUCCESS.search(text):
                evidence = save_evidence(page, job, 'confirmed')
                return evidence
            if SECURITY.search(text):
                self.security_handoff(page, job)
                last_signature = ''
                repeated = 0
                continue
            if re.search(r'authenticator|authentication app', text, re.I) and any(
                    OTP.search(f['label']) or f['autocomplete'] == 'one-time-code' for _,s in snapshots for f in s['fields']):
                host = urlsplit(page.url).hostname
                if not mfa.secret(f'TOTP:{host}:{profile["email"]}'):
                    self.security_handoff(page, job, re.compile(r'authenticator|authentication app', re.I))
                    continue
            if not link_followed and re.search(r'(?:click|follow|open)[^\n.]{0,80}(?:verification|confirmation|activation|verify)[^\n.]{0,80}link|(?:verification|confirmation|activation) link[^\n.]{0,80}(?:email|sent)', text, re.I):
                self.follow_verification_link(page, job, started)
                link_followed = True
                continue
            if submitted and any(OTP.search(f['label']) or f['autocomplete'] == 'one-time-code'
                                 for _, s in snapshots for f in s['fields']):
                code_frame = next(f for f, s in snapshots if any(OTP.search(x['label']) or x['autocomplete'] == 'one-time-code' for x in s['fields']))
                code = self.verification_code(job, profile, urlsplit(code_frame.url).hostname or urlsplit(page.url).hostname, '', text, started)
                for frame, state in snapshots:
                    for field in state['fields']:
                        if OTP.search(field['label']) or field['autocomplete'] == 'one-time-code':
                            frame.locator(f'[data-agent-field="{field["id"]}"]').fill(code)
                verifies = [(f, b) for f, s in snapshots for b in s['buttons']
                            if re.fullmatch(r'verify|verify (?:email|code)|confirm code', b['text'], re.I)]
                if len(verifies) != 1:
                    raise NeedsReview('Verification requires an unrecognized action')
                frame, button = verifies[0]
                frame.locator(f'[data-agent-button="{button["id"]}"]').click()
                continue
            if submitted:
                # Never click Submit twice after an ambiguous network response.
                for _ in range(8):
                    page.wait_for_timeout(1000)
                    text = '\n'.join(f.locator('body').inner_text() for f in page.frames)
                    if SUCCESS.search(text):
                        return save_evidence(page, job, 'confirmed')
                raise NeedsReview('Submission was attempted but confirmation is uncertain; check before retrying')
            if re.search(r'job (?:is no longer|has been filled)|position (?:is no longer|has been filled)', text, re.I):
                raise NeedsReview('This posting appears to be closed')

            signature = hashlib.sha256(json.dumps([
                (s['fields'], s['buttons'], s['text'][-3000:]) for _, s in snapshots], sort_keys=True).encode()).hexdigest()
            repeated = repeated + 1 if signature == last_signature else 0
            last_signature = signature
            if repeated >= 2:
                raise NeedsReview('Form did not advance; inspect the saved screenshot')

            unresolved = []
            has_password = any(f['type'] == 'password' for _, s in snapshots for f in s['fields'])
            creating = has_password and bool(re.search(r'create (?:an )?account|confirm password|sign up', text, re.I))
            host = urlsplit(page.url).hostname
            kind, sender_domains = platform(host)
            password_key = f'ACCOUNT:{host}:{profile["email"]}'
            password = None
            if has_password:
                password = secret(password_key)
                if not password and creating:
                    password = 'Aa9!' + secrets.token_urlsafe(24)
                    set_secret(password_key, password)
                elif not password:
                    raise NeedsReview('Existing account login needs a saved password; add it in Settings')
            filled_any = False
            for frame, state in snapshots:
                groups = {}
                for field in state['fields']:
                    if field['type'] == 'radio':
                        groups.setdefault(field['name'] or field['label'], []).append(field)
                handled_groups = set()
                for field in state['fields']:
                    loc = frame.locator(f'[data-agent-field="{field["id"]}"]')
                    label = field['label'].strip().rstrip('*').strip()
                    try:
                        saved = ai.saved_answer(label, overrides)
                        if field['type'] == 'checkbox' and DECISION.search(label) and saved is None:
                            if field['checked'] or field['required']:
                                unresolved.append(label)
                            continue
                        if field['type'] == 'file':
                            if 'cover' in label.lower() or 'additional' in label.lower():
                                if field['required']:
                                    unresolved.append(label)
                                continue
                            if not re.search(r'resume|cv|curriculum', label, re.I):
                                if field['required']:
                                    unresolved.append(label or 'Unlabeled file upload')
                                continue
                            resume = profile['resumes'][job['resume']]
                            path = Path(resume['path']).resolve()
                            if not path.is_file() or not path.is_relative_to((DATA / 'resumes').resolve()):
                                raise NeedsReview('Selected resume is missing from the local resume directory')
                            loc.set_input_files(str(path))
                            resume_uploaded = True
                            filled_any = True
                            continue
                        if field['type'] == 'password':
                            loc.fill(password)
                            filled_any = True
                            continue
                        if field['checked'] or (field['value'] and field['type'] not in ('checkbox', 'radio')):
                            # Reconcile prefilled profile text below; never overwrite a saved choice silently.
                            if field['type'] in ('checkbox', 'radio'):
                                continue
                            if not label or not ai.factual_answer(label, profile):
                                continue
                        if not label:
                            if field['required']:
                                unresolved.append('Unlabeled required field')
                            continue
                        if field['type'] == 'radio':
                            key = field['name'] or field['label']
                            if key in handled_groups:
                                continue
                            handled_groups.add(key)
                            group = groups[key]
                            if any(f['checked'] for f in group):
                                continue
                            value = ai.answer(label, [f['option'] for f in group], profile, job, overrides)
                            chosen = next(f for f in group if f['option'] == value)
                            frame.locator(f'[data-agent-field="{chosen["id"]}"]').check()
                        elif field['type'] == 'checkbox':
                            if saved is None:
                                if field['required']:
                                    unresolved.append(label)
                                continue
                            if saved.lower() in ('yes', 'true', 'agree'):
                                loc.check()
                            elif field['required']:
                                unresolved.append(label)
                        elif OTP.search(label) or field['autocomplete'] == 'one-time-code':
                            code = self.verification_code(job, profile, urlsplit(frame.url).hostname or host, label, text, started)
                            loc.fill(code)
                        elif field['tag'] == 'select':
                            if field.get('multiple') and saved is not None:
                                values = [v.strip() for v in saved.split(';') if v.strip()]
                                if not values or not all(v in field['options'] for v in values):
                                    raise NeedsReview('Saved multiple selections do not match the available options', [label])
                                loc.select_option(label=values)
                            else:
                                value = ai.answer(label, field['options'], profile, job, overrides)
                                loc.select_option(label=value)
                        elif field['type'] == 'combobox' or loc.get_attribute('role') == 'combobox':
                            loc.click()
                            choices = frame.get_by_role('option')
                            options = choices.all_text_contents()
                            if not options:
                                value = ai.answer(label, [], profile, job, overrides)
                                loc.fill(value)
                                page.wait_for_timeout(700)
                                options = choices.all_text_contents()
                            value = ai.answer(label, options, profile, job, overrides)
                            if not options:
                                raise NeedsReview('Custom selector needs a choice', [label])
                            frame.get_by_role('option', name=value, exact=True).click()
                        elif field['type'] in ('text', 'email', 'tel', 'url', 'number', 'date', 'textarea', 'search', 'textbox') or field['tag'] == 'textarea':
                            value = profile['email'] if has_password and field['type'] == 'email' else ai.answer(label, [], profile, job, overrides)
                            loc.fill(value)
                        else:
                            if field['required']:
                                unresolved.append(label)
                            continue
                        filled_any = True
                    except NeedsReview as exc:
                        if field['required'] or field['type'] in ('radio', 'password'):
                            unresolved.extend(exc.questions or [label])
                    except Exception:
                        if field['required']:
                            unresolved.append(label)
            if unresolved:
                raise NeedsReview('Required answers or form controls need your input', sorted(set(unresolved)))

            candidates = []
            for frame, state in snapshots:
                for button in state['buttons']:
                    name = button['text']
                    if has_password:
                        good = re.fullmatch(r'create (?:an )?account|sign up|sign in|log in|register', name, re.I)
                    else:
                        good = NEXT.fullmatch(name) or SUBMIT.fullmatch(name) or ENTER.fullmatch(name)
                    if good:
                        candidates.append((frame, button))
            # Prefer multi-step navigation over a final submission on the same view.
            nexts = [(f, b) for f, b in candidates if NEXT.fullmatch(b['text'])]
            if nexts:
                candidates = nexts
            if len(candidates) != 1:
                raise NeedsReview('Application navigation is ambiguous or unsupported')
            frame, button = candidates[0]
            name = button['text']
            if button['href']:
                public_url(button['href'])
            final = bool(SUBMIT.fullmatch(name)) and not has_password
            if name.lower() == 'apply now' and not resume_uploaded and not any(s['fields'] for _, s in snapshots):
                final = False
            if final:
                implied_agreement = re.search(r'by (?:clicking|submitting|continuing|creating)[^\n.]{0,200}(?:agree|consent|certify)[^\n.]{0,200}', text, re.I)
                if implied_agreement and overrides.get(implied_agreement.group(0), '').lower() not in ('yes', 'agree'):
                    raise NeedsReview('Submission includes an agreement requiring your decision', [implied_agreement.group(0)])
                invalid = []
                for f, _ in snapshots:
                    invalid.extend(f.evaluate("() => [...document.querySelectorAll('input,select,textarea')].filter(e => e.willValidate && !e.checkValidity()).map(e => e.getAttribute('aria-label') || e.name || 'Required field')"))
                if invalid:
                    raise NeedsReview('Form validation is incomplete', invalid)
                if SUCCESS.search(text):
                    raise NeedsReview('Page already contains confirmation text; verify application state')
                if not resume_uploaded:
                    raise NeedsReview('Could not verify a resume attachment before submission')
                db.update(job['id'], attempted=1, evidence=save_evidence(page, job, 'before-submit'))
                submitted = True
            if has_password and creating:
                implied_agreement = re.search(r'by (?:clicking|submitting|continuing|creating)[^\n.]{0,200}(?:agree|consent)[^\n.]{0,200}', text, re.I)
                if implied_agreement and overrides.get(implied_agreement.group(0), '').lower() not in ('yes', 'agree'):
                    raise NeedsReview('Account creation includes an agreement requiring your decision', [implied_agreement.group(0)])
                if account_sent:
                    raise NeedsReview('Account creation did not complete; verify its status before retrying')
                account_sent = True
            frame.locator(f'[data-agent-button="{button["id"]}"]').click()
        raise NeedsReview('Application exceeded the supported number of steps')
