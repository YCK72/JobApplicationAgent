from agent import ai, db
from agent.config import Settings
import agent.worker as work


def prepare(monkeypatch, result):
    from types import SimpleNamespace
    monkeypatch.setattr(work,'profile',lambda:{'email':'test@example.org','resumes':{'sde':{'enabled':True}}})
    monkeypatch.setattr(work,'secret',lambda name:'configured')
    monkeypatch.setattr(work.discovery,'discover',lambda c:0)
    monkeypatch.setattr(work.ai,'fit',lambda j,p:result)
    monkeypatch.setattr(work.ai,'client',lambda:SimpleNamespace(models=SimpleNamespace(retrieve=lambda model:None)))
    monkeypatch.setattr(work.gmail,'service',lambda:None)
    monkeypatch.setattr(work.reports,'export',lambda:None)
    worker=work.Worker()
    monkeypatch.setattr(worker.pause,'wait',lambda seconds:False)
    return worker


def fit(**changes):
    return ai.Fit(**dict(dict(relevant=True,us_eligible=True,sponsorship_excluded=False,
        large_tech_company=False,resume='sde',score=85,reason='Relevant US role'),**changes))


def test_large_tech_never_reaches_browser_without_approval(job,monkeypatch):
    worker=prepare(monkeypatch,fit(large_tech_company=True))
    monkeypatch.setattr(work.BrowserApplicant,'apply',lambda *a: (_ for _ in ()).throw(AssertionError('Must not submit')))
    worker.cycle(Settings())
    assert db.get(job['id'])['status']=='needs_review'
    assert 'Major tech' in db.get(job['id'])['reason']


def test_approved_application_is_recorded_only_after_browser_confirmation(job,monkeypatch):
    worker=prepare(monkeypatch,fit(large_tech_company=True))
    db.update(job['id'],approved=1)
    monkeypatch.setattr(work.BrowserApplicant,'apply',lambda *a:'evidence/confirmed.png')
    worker.cycle(Settings())
    assert db.get(job['id'])['status']=='applied'
    assert db.get(job['id'])['applied_at']


def test_non_us_job_never_reaches_browser(job,monkeypatch):
    worker=prepare(monkeypatch,fit(us_eligible=False))
    monkeypatch.setattr(work.BrowserApplicant,'apply',lambda *a: (_ for _ in ()).throw(AssertionError('Must not submit')))
    worker.cycle(Settings())
    assert db.get(job['id'])['status']=='skipped'


def test_attempt_history_survives_status_changes(job):
    db.update(job['id'],attempted=1)
    db.update(job['id'],status='needs_review')
    db.update(job['id'],attempted=1)
    with db.connection() as c:
        assert c.execute('SELECT count(*) FROM attempts').fetchone()[0]==1
    db.update(job['id'],attempted=0)
    db.update(job['id'],attempted=1)
    with db.connection() as c:
        assert c.execute('SELECT count(*) FROM attempts').fetchone()[0]==2
