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
