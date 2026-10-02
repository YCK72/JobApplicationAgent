import threading

import pytest
from playwright.sync_api import sync_playwright

from agent import browser, db
from agent.policy import NeedsReview


@pytest.fixture
def page():
    with sync_playwright() as pw:
        b=pw.chromium.launch(headless=True)
        p=b.new_page()
        p.route('https://jobs.example.org/**', lambda route: route.fulfill(body='<html><body></body></html>', content_type='text/html'))
        p.goto('https://jobs.example.org/123')
        yield p
        b.close()


def profile_with_resume(tmp_path):
    directory=tmp_path/'resumes'
    directory.mkdir()
    (directory/'sde.pdf').write_bytes(b'%PDF-1.4\n%%EOF')
    return {'name':'Test Candidate','email':'candidate@example.org',
            'resumes':{'sde':{'path':str(directory/'sde.pdf'),'enabled':True}}}


def test_single_confirmed_submission(page,job,isolated_data,monkeypatch):
    monkeypatch.setattr(browser,'public_url',lambda x:x)
    page.set_content('''<form onsubmit="event.preventDefault(); window.count=(window.count||0)+1;document.body.innerHTML='<h1>Thank you for applying</h1>'">
    <label>Full name<input required></label><label>Email<input type=email required></label>
    <label>Resume<input type=file required></label><button type=submit>Submit application</button></form>''')
    evidence=browser.BrowserApplicant(threading.Event()).run(page,job,profile_with_resume(isolated_data))
    assert page.evaluate('window.count') == 1
    assert db.get(job['id'])['attempted'] == 1
    assert evidence.endswith('confirmed.png')


def test_saved_checkbox_answer_is_reused(page,job,isolated_data,monkeypatch):
    monkeypatch.setattr(browser,'public_url',lambda x:x)
    profile=profile_with_resume(isolated_data)
    profile['answers']={'I agree to the privacy policy':'Yes'}
    page.set_content('''<form onsubmit="event.preventDefault();document.body.innerHTML='Thank you for applying'">
    <label>Resume<input type=file required></label>
    <label>I agree to the privacy policy<input type=checkbox required></label>
    <button type=submit>Submit application</button></form>''')
    evidence=browser.BrowserApplicant(threading.Event()).run(page,job,profile)
    assert evidence.endswith('confirmed.png')


def test_required_decision_prevents_submission(page,job,isolated_data,monkeypatch):
    monkeypatch.setattr(browser,'public_url',lambda x:x)
    page.set_content('''<form onsubmit="event.preventDefault();window.submitted=true">
    <label>Full name<input required></label><label>Resume<input type=file required></label>
    <label>Expected salary<input required></label><button>Submit application</button></form>''')
    with pytest.raises(NeedsReview) as exc:
        browser.BrowserApplicant(threading.Event()).run(page,job,profile_with_resume(isolated_data))
    assert 'Expected salary' in exc.value.questions
    assert not page.evaluate('Boolean(window.submitted)')
    assert db.get(job['id'])['attempted'] == 0


def test_review_page_submission_is_tracked(page,job,isolated_data,monkeypatch):
    monkeypatch.setattr(browser,'public_url',lambda x:x)
    page.set_content('<label>Resume<input type=file></label><button>Continue</button>')
    page.evaluate('''() => {document.querySelector('button').onclick=()=>{document.body.innerHTML='<h1>Review application</h1><button>Submit application</button>';document.querySelector('button').onclick=()=>{document.body.innerHTML='Thank you for applying';};};}''')
    evidence=browser.BrowserApplicant(threading.Event()).run(page,job,profile_with_resume(isolated_data))
    assert db.get(job['id'])['attempted'] == 1
    assert evidence.endswith('confirmed.png')


def test_uncertain_submission_is_not_retried(page,job,isolated_data,monkeypatch):
    monkeypatch.setattr(browser,'public_url',lambda x:x)
    page.set_content('''<label>Resume<input type=file></label><button onclick="window.count=(window.count||0)+1">Submit application</button>''')
    with pytest.raises(NeedsReview,match='confirmation is uncertain'):
        browser.BrowserApplicant(threading.Event()).run(page,job,profile_with_resume(isolated_data))
    assert page.evaluate('window.count') == 1
    assert db.get(job['id'])['attempted'] == 1


def test_otp_can_complete_pending_submission(page,job,isolated_data,monkeypatch):
    monkeypatch.setattr(browser,'public_url',lambda x:x)
    monkeypatch.setattr(browser.gmail,'verification_code',lambda *a:'123456')
    page.set_content('<label>Resume<input type=file></label><button>Submit application</button>')
    page.evaluate('''() => {document.querySelector('button').onclick=()=>{document.body.innerHTML='<label>Verification code<input autocomplete="one-time-code"></label><button>Verify code</button>';document.querySelector('button').onclick=()=>{if(document.querySelector('input').value==='123456')document.body.innerHTML='Thank you for applying';};};}''')
    evidence=browser.BrowserApplicant(threading.Event()).run(page,job,profile_with_resume(isolated_data))
    assert evidence.endswith('confirmed.png')
    with db.connection() as c:
        assert c.execute('SELECT count(*) FROM attempts').fetchone()[0]==1


def test_prechecked_agreement_needs_decision(page,job,isolated_data,monkeypatch):
    monkeypatch.setattr(browser,'public_url',lambda x:x)
    page.set_content('<label>Resume<input type=file></label><label>I agree to terms<input type=checkbox checked></label><button>Submit application</button>')
    with pytest.raises(NeedsReview) as exc:
        browser.BrowserApplicant(threading.Event()).run(page,job,profile_with_resume(isolated_data))
    assert 'I agree to terms' in exc.value.questions
    assert db.get(job['id'])['attempted']==0


def test_account_creation_uses_email_and_unique_saved_password(page,job,isolated_data,monkeypatch):
    monkeypatch.setattr(browser,'public_url',lambda x:x)
    saved={}
    monkeypatch.setattr(browser,'secret',lambda key:saved.get(key))
    monkeypatch.setattr(browser,'set_secret',lambda key,value:saved.update({key:value}))
    page.set_content('<h1>Create account</h1><label>Email<input type=email required></label><label>Password<input type=password required></label><button>Create account</button>')
    page.evaluate('''() => {document.querySelector('button').onclick=()=>{window.accountEmail=document.querySelector('input[type=email]').value;document.body.innerHTML='<label>Resume<input type=file></label><button>Submit application</button>';document.querySelector('button').onclick=()=>{document.body.innerHTML='Thank you for applying';};};}''')
    browser.BrowserApplicant(threading.Event()).run(page,job,profile_with_resume(isolated_data))
    assert page.evaluate('window.accountEmail')=='candidate@example.org'
    assert len(saved)==1
    assert len(next(iter(saved.values())))>=20


def test_authenticator_mfa_then_application(page,job,isolated_data,monkeypatch):
    monkeypatch.setattr(browser,'public_url',lambda x:x)
    monkeypatch.setattr(browser.mfa,'secret',lambda key:'configured')
    monkeypatch.setattr(browser.mfa,'account_code',lambda *args:'123456')
    page.set_content('<h1>Authenticator</h1><label>Authenticator code<input required></label><button>Verify code</button>')
    page.evaluate('''() => {document.querySelector('button').onclick=()=>{if(document.querySelector('input').value==='123456'){document.body.innerHTML='<label>Resume<input type=file></label><button>Submit application</button>';document.querySelector('button').onclick=()=>document.body.innerHTML='Thank you for applying';}};}''')
    assert browser.BrowserApplicant(threading.Event()).run(page,job,profile_with_resume(isolated_data)).endswith('confirmed.png')


def test_verification_link_then_application(page,job,isolated_data,monkeypatch):
    monkeypatch.setattr(browser,'public_url',lambda x:x)
    followed=[]
    def follow(self,page,job,started):
        followed.append(True)
        page.set_content('''<label>Resume<input type=file></label><button onclick="document.body.innerHTML='Thank you for applying'">Submit application</button>''')
    monkeypatch.setattr(browser.BrowserApplicant,'follow_verification_link',follow)
    page.set_content('<p>Verification link has been sent to your email</p>')
    assert browser.BrowserApplicant(threading.Event()).run(page,job,profile_with_resume(isolated_data)).endswith('confirmed.png')
    assert followed == [True]


def test_handoff_resumes_same_application(page,job,isolated_data,monkeypatch):
    from agent.config import Settings
    monkeypatch.setattr(browser,'public_url',lambda x:x)
    monkeypatch.setattr(browser,'settings',lambda:Settings(interactive_handoff=True))
    page.set_content('<h1>Verify you are human</h1>')
    page.evaluate('''() => setTimeout(()=>{document.body.innerHTML='<label>Resume<input type=file></label><button>Submit application</button>';document.querySelector('button').onclick=()=>document.body.innerHTML='Thank you for applying';},1500)''')
    assert browser.BrowserApplicant(threading.Event()).run(page,job,profile_with_resume(isolated_data)).endswith('confirmed.png')
    with db.connection() as c:
        assert any('resume when it clears' in r['message'] for r in c.execute('SELECT message FROM events'))


def test_multi_select_and_contenteditable(page,job,isolated_data,monkeypatch):
    monkeypatch.setattr(browser,'public_url',lambda x:x)
    profile=profile_with_resume(isolated_data)
    profile['answers']={'Skills':'Python;SQL','Motivation':'I build Python services.'}
    page.set_content('''<label>Resume<input type=file></label><label>Skills<select multiple required><option>Python</option><option>SQL</option><option>Rust</option></select></label>
    <div role=textbox contenteditable=true aria-label=Motivation aria-required=true></div><button onclick="window.chosen=[...document.querySelector('select').selectedOptions].map(o=>o.textContent);window.motivation=document.querySelector('[role=textbox]').innerText;document.body.innerHTML='Thank you for applying'">Submit application</button>''')
    try:
        evidence=browser.BrowserApplicant(threading.Event()).run(page,job,profile)
    except NeedsReview as exc:
        pytest.fail(f'{exc}: {exc.questions}')
    assert evidence.endswith('confirmed.png')
    assert page.evaluate('window.chosen')==['Python','SQL']
    assert page.evaluate('window.motivation')=='I build Python services.'


def test_aria_checkbox_and_radio_group(page,job,isolated_data,monkeypatch):
    monkeypatch.setattr(browser,'public_url',lambda x:x)
    profile=profile_with_resume(isolated_data)
    profile['answers']={'I agree to terms':'Yes','Work arrangement':'Remote'}
    page.set_content('''<label>Resume<input type=file></label>
    <div role=checkbox aria-label="I agree to terms" aria-required=true aria-checked=false onclick="this.setAttribute('aria-checked','true')">I agree to terms</div>
    <div role=radiogroup aria-label="Work arrangement"><div role=radio aria-label=Remote aria-checked=false onclick="this.setAttribute('aria-checked','true')">Remote</div><div role=radio aria-label=Onsite aria-checked=false>Onsite</div></div>
    <button onclick="window.agreed=document.querySelector('[role=checkbox]').getAttribute('aria-checked');window.remote=document.querySelector('[role=radio]').getAttribute('aria-checked');document.body.innerHTML='Thank you for applying'">Submit application</button>''')
    assert browser.BrowserApplicant(threading.Event()).run(page,job,profile).endswith('confirmed.png')
    assert page.evaluate('window.agreed')=='true'
    assert page.evaluate('window.remote')=='true'


def test_verification_redirect_cannot_leave_career_host(page,job,monkeypatch):
    from playwright.sync_api import Error
    monkeypatch.setattr(browser,'public_url',lambda x:x)
    monkeypatch.setattr(browser.gmail,'verification_link',lambda *args:'https://jobs.example.org/verify?token=test')
    page.route('https://jobs.example.org/verify?token=test',lambda route:route.fulfill(status=302,headers={'Location':'https://evil.example/verify?token=test'}))
    reached=[]
    page.route('https://evil.example/**',lambda route:(reached.append(True),route.fulfill(body='evil')))
    with pytest.raises((Error,NeedsReview)):
        browser.BrowserApplicant(threading.Event()).follow_verification_link(page,job,0)
    assert not reached
