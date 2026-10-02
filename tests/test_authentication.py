import base64
import threading
import pytest
from fastapi.testclient import TestClient
from agent import ai, config, db, gmail, mfa, server
from agent import browser
from agent.policy import NeedsReview


@pytest.mark.parametrize('timestamp,expected', [(59,'94287082'),(1111111109,'07081804'),(20000000000,'65353130')])
def test_rfc_totp_vectors(timestamp,expected):
    seed=base64.b32encode(b'12345678901234567890').decode()
    assert mfa.totp(seed,timestamp,digits=8)==expected


def verification_message(body, mime='text/html'):
    return {'internalDate':'2000000','payload':{'mimeType':mime,'headers':[
        {'name':'From','value':'noreply@ashbyhq.com'}, {'name':'To','value':'candidate@example.org'},
        {'name':'Authentication-Results','value':'mx.google.com; dkim=pass header.d=ashbyhq.com'}],
        'body':{'data':base64.urlsafe_b64encode(body.encode()).decode()}}}


def link(message):
    return gmail.extract_verification_link(message,recipient='candidate@example.org',sender_domains=['ashbyhq.com'],
        company='Example Research',since=1900,allowed_hosts=['jobs.ashbyhq.com'])


def test_authenticated_link_with_html_query_parameters():
    message=verification_message('Example Research: verify your email <a href="https://jobs.ashbyhq.com/verify?token=test&amp;id=123">Confirm</a>')
    assert link(message)=='https://jobs.ashbyhq.com/verify?token=test&id=123'


@pytest.mark.parametrize('url', ['https://evil.example/verify?token=test','https://jobs.ashbyhq.com/reset-password',
    'https://jobs.ashbyhq.com/verify?redirect=https://evil.example', 'http://jobs.ashbyhq.com/verify',
    'https://user:password@jobs.ashbyhq.com/verify','https://jobs.ashbyhq.com:bad/verify'])
def test_untrusted_verification_links_are_rejected(url):
    assert link(verification_message(f'Example Research: verify email <a href="{url}">Verify</a>')) is None


def test_ambiguous_or_unauthenticated_link_is_rejected():
    msg=verification_message('Example Research: verify email <a href="https://jobs.ashbyhq.com/verify?token=a">Verify</a><a href="https://jobs.ashbyhq.com/verify?token=b">Verify</a>')
    assert link(msg) is None
    msg=verification_message('Example Research verify email https://jobs.ashbyhq.com/verify?token=a','text/plain')
    msg['payload']['headers'][-1]['value']='dkim=fail'
    assert link(msg) is None


def test_answers_ignore_formatting_but_preserve_negation():
    assert ai.saved_answer('Expected salary?',{'Expected salary':'90000'})=='90000'
    assert ai.saved_answer('I do not require sponsorship',{'I require sponsorship':'Yes'}) is None
    with pytest.raises(NeedsReview):
        ai.saved_answer('expected salary!',{'Expected salary':'90000','Expected salary?':'100000'})


def test_review_answers_are_remembered_only_when_requested(job, isolated_data):
    client=TestClient(server.app)
    db.update(job['id'],status='needs_review')
    response=client.post(f'/api/jobs/{job["id"]}/resolve',json={'action':'retry','answers':{'Expected salary':'90000'}},headers={'X-Local-Request':'job-agent'})
    assert response.status_code==200
    assert 'answers' not in config.profile()
    db.update(job['id'],status='needs_review')
    response=client.post(f'/api/jobs/{job["id"]}/resolve',json={'action':'retry','answers':{'Expected salary':'95000'},'remember_answers':True},headers={'X-Local-Request':'job-agent'})
    assert response.status_code==200
    assert config.profile()['answers']['Expected salary']=='95000'


def test_mfa_seed_stays_in_vault(isolated_data,monkeypatch):
    saved={}
    config.write_json(isolated_data/'profile.json',{'email':'candidate@example.org'})
    monkeypatch.setattr(server,'public_url',lambda value:value)
    monkeypatch.setattr(server,'set_secret',lambda name,value:saved.update({name:value}))
    seed=base64.b32encode(b'12345678901234567890').decode()
    response=TestClient(server.app).post('/api/mfa',json={'site':'https://jobs.ashbyhq.com','seed':seed},headers={'X-Local-Request':'job-agent'})
    assert response.status_code==200
    assert saved=={'TOTP:jobs.ashbyhq.com:candidate@example.org':seed}
    assert seed not in (isolated_data/'profile.json').read_text()


def test_verification_redirect_is_checked_before_external_request(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(browser,'public_url',lambda value:value)
    calls=[]
    class Route:
        request=SimpleNamespace(url='https://jobs.example.org/verify?token=test')
        def fetch(self,**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(status=302,headers={'location':'https://evil.example/verify?token=test'})
    with pytest.raises(NeedsReview,match='host or protocol'):
        browser.verification_response(Route(),'jobs.example.org')
    assert len(calls)==1
    assert calls[0]['max_redirects']==0
    assert 'evil.example' not in calls[0]['url']


def test_same_host_verification_redirect_can_complete(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(browser,'public_url',lambda value:value)
    calls=[]
    class Route:
        request=SimpleNamespace(url='https://jobs.example.org/verify?token=test')
        def fetch(self,**kwargs):
            calls.append(kwargs['url'])
            return SimpleNamespace(status=302,headers={'location':'/confirmed'}) if len(calls)==1 else SimpleNamespace(status=200,headers={})
    assert browser.verification_response(Route(),'jobs.example.org').status==200
    assert calls==['https://jobs.example.org/verify?token=test','https://jobs.example.org/confirmed']
