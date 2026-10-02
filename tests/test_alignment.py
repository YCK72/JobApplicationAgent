import pytest
from fastapi.testclient import TestClient
from agent import ai, policy, server, tailoring, config, db


@pytest.mark.parametrize('title', ['Senior Software Engineer', 'Sr. Data Scientist', 'Lead ML Engineer', 'IT Manager'])
def test_senior_roles_excluded(title):
    assert policy.coarse_reject({'title': title, 'description': ''})


def test_no_invented_candidate_preferences():
    assert policy.factual_answer('Authorized to work in the US?', {}) is None
    assert policy.factual_answer('Willing to relocate?', {}) is None
    assert policy.factual_answer('Will you require sponsorship?', {}) is None
    assert policy.factual_answer('Will you require sponsorship?', {'requires_sponsorship': False}) == 'No'


def test_reusable_answers(job):
    assert ai.answer('What salary do you expect?', [], {'answers': {'What salary do you expect?': '90000'}}, job, {}) == '90000'


def test_tailoring_keeps_every_line_and_escapes_html():
    blocks=tailoring.sections('Candidate\nemail@example.org\nEDUCATION\nBS Computer Science\nEXPERIENCE\nAcme <script>\nBuilt Python services\nSKILLS\nPython, SQL')
    assert len(blocks) == 4
    html=tailoring.document(blocks, [0,3,2,1])
    assert 'Acme &lt;script&gt;' in html
    assert html.index('Python, SQL') < html.index('Built Python services')
    for order in ([0,1,1,2], [0,1], [1,0,2,3]):
        with pytest.raises(policy.NeedsReview):
            tailoring.document(blocks, order)


def test_profile_edit_preserves_imported_resumes(isolated_data):
    config.write_json(isolated_data/'profile.json', {'resumes': {'sde': {'path': 'existing.pdf'}}})
    response=TestClient(server.app).post('/api/profile', json={'name':'Candidate','email':'test@example.org', 'authorized_to_work_us':False}, headers={'X-Local-Request':'job-agent'})
    assert response.status_code == 200
    assert config.profile()['resumes']['sde']['path'] == 'existing.pdf'
    assert config.profile()['authorized_to_work_us'] is False


def test_bad_resume_is_not_written(isolated_data):
    response=TestClient(server.app).post('/api/resumes', json={'kind':'sde','content':'not base64'}, headers={'X-Local-Request':'job-agent'})
    assert response.status_code == 422
    assert not (isolated_data/'resumes').exists()


def test_major_tech_can_apply_without_gmail(job, monkeypatch):
    from test_worker import prepare, fit
    import agent.worker as work
    worker=prepare(monkeypatch,fit(large_tech_company=True))
    monkeypatch.setattr(work,'secret', lambda name: 'key' if name=='OPENAI_API_KEY' else None)
    monkeypatch.setattr(work.BrowserApplicant,'apply',lambda *args: 'evidence/confirmed.png')
    worker.cycle(config.Settings())
    assert db.get(job['id'])['status'] == 'applied'


def test_prepared_pdf_contains_all_facts_and_caches(job, tmp_path, monkeypatch):
    from pathlib import Path
    from pypdf import PdfReader
    monkeypatch.setattr(tailoring, 'DATA', tmp_path)
    calls=[]
    def rank(*args):
        calls.append(True)
        return tailoring.SectionOrder(order=[0,3,2,1])
    monkeypatch.setattr(ai, 'structured', rank)
    profile={'resumes':{'sde':{'enabled':True,'path':'original.pdf',
        'text':'Candidate\nemail@example.org\nEDUCATION\nBS Computer Science\nEXPERIENCE\nAcme Research\nBuilt Python services\nSKILLS\nPython, SQL'}}}
    prepared=tailoring.prepare(job,profile)
    path=Path(prepared['resumes']['sde']['path'])
    assert path.is_file()
    text='\n'.join(page.extract_text() for page in PdfReader(path).pages)
    assert 'BS Computer Science' in text and 'Built Python services' in text
    assert text.index('Python, SQL') < text.index('Built Python services')
    assert profile['resumes']['sde']['path']=='original.pdf'
    assert tailoring.prepare(job,profile)['resumes']['sde']['path']==str(path)
    assert len(calls)==1
