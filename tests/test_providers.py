from types import SimpleNamespace
import httpx
import pytest
from openai import RateLimitError
from agent import ai, config, db
import agent.worker as work


def test_provider_routes_and_schema_validation(monkeypatch):
    calls = []
    def fake_client(provider='groq'):
        def parse(**kwargs):
            calls.append((provider, kwargs))
            parsed = ai.Fit(relevant=True, us_eligible=True, sponsorship_excluded=False,
                large_tech_company=False, resume='sde', score=90, reason='Junior US role') if provider == 'gemini' else ai.Answer(answer='Python', needs_decision=False, evidence=['Python'], reason='Documented')
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed, refusal=None))])
        return SimpleNamespace(beta=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=parse))))
    monkeypatch.setattr(ai, 'client', fake_client)
    monkeypatch.setattr(ai, 'settings', lambda: config.Settings())
    assert ai.fit({'title':'Junior Engineer'}, {'skills':'Python'}).relevant
    assert ai.answer('Describe your skills', [], {'skills':'Python'}, {'company':'Example','title':'Junior','description':'Python'}, {}) == 'Python'
    assert [c[0] for c in calls] == ['gemini', 'groq']
    assert calls[0][1]['model'] == 'gemini-3.1-flash-lite'
    assert calls[1][1]['model'] == 'openai/gpt-oss-20b'
    assert calls[0][1]['response_format'] is ai.Fit


def test_provider_endpoints_never_use_openai(monkeypatch):
    calls = []
    monkeypatch.setattr(ai, 'secret', lambda name: name)
    monkeypatch.setattr(ai, 'OpenAI', lambda **kwargs: calls.append(kwargs))
    ai.client('gemini')
    ai.client('groq')
    assert calls[0]['api_key'] == 'GEMINI_API_KEY'
    assert calls[1]['api_key'] == 'GROQ_API_KEY'
    assert 'googleapis.com' in calls[0]['base_url']
    assert 'api.groq.com' in calls[1]['base_url']


def test_rate_limit_is_sanitized(monkeypatch):
    def parse(**kwargs):
        raise RateLimitError('private candidate payload', response=httpx.Response(429, request=httpx.Request('POST','https://example.org')), body=None)
    monkeypatch.setattr(ai, 'client', lambda provider: SimpleNamespace(beta=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=parse)))))
    with pytest.raises(ai.ProviderUnavailable) as exc:
        ai.structured(ai.Fit, 'instructions', {}, provider='gemini')
    assert 'Gemini' in str(exc.value)
    assert 'private candidate' not in str(exc.value)


def test_provider_failure_stops_cycle_and_preserves_queue(job, monkeypatch, isolated_data):
    monkeypatch.setattr(work, 'DATA', isolated_data)
    monkeypatch.setattr(work, 'profile', lambda:{'email':'test@example.org','resumes':{'sde':{'enabled':True}}})
    monkeypatch.setattr(work, 'secret', lambda name:'configured')
    monkeypatch.setattr(work.discovery, 'discover', lambda c:0)
    monkeypatch.setattr(work.reports, 'export', lambda:None)
    calls = []
    def fail(j,p):
        calls.append(j['id'])
        raise ai.ProviderUnavailable('Gemini quota reached')
    monkeypatch.setattr(ai, 'fit', fail)
    worker = work.Worker()
    worker.cycle(config.Settings(enabled=True))
    assert len(calls) == 1
    assert db.get(job['id'])['status'] == 'queued'
    assert worker.pause.is_set()
    assert not config.settings().enabled
