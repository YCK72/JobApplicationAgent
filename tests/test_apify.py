import httpx
import pytest
from agent import apify_source, discovery, db
from agent.policy import NeedsReview


def test_actor_resumes_running_run_without_second_start(tmp_path, monkeypatch):
    monkeypatch.setattr(apify_source, 'DATA', tmp_path)
    monkeypatch.setattr(apify_source, 'secret', lambda name: 'test-token')
    calls=[]
    def handler(request):
        calls.append(request.method)
        if request.method == 'POST':
            return httpx.Response(201, json={'data': {'id':'run123'}})
        return httpx.Response(200, json={'data': {'status': 'RUNNING'}})
    source={'board':'owner~actor','input':{'urls':['https://www.linkedin.com/jobs/search/']}}
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert apify_source.dataset(client,source) is None
        assert apify_source.dataset(client,source) is None
    assert calls == ['POST','GET','GET']


def test_ambiguous_actor_start_is_not_retried(tmp_path, monkeypatch):
    monkeypatch.setattr(apify_source, 'DATA', tmp_path)
    monkeypatch.setattr(apify_source, 'secret', lambda name: 'test-token')
    def handler(request):
        raise httpx.ReadTimeout('timed out')
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.ReadTimeout):
            apify_source.dataset(client,{'board':'owner~actor'})
        with pytest.raises(NeedsReview, match='ambiguous'):
            apify_source.dataset(client,{'board':'owner~actor'})


def test_dataset_import_uses_application_url_and_deduplicates(monkeypatch):
    from agent.config import Settings
    original_client=httpx.Client
    def handler(request):
        return httpx.Response(200,json=[{'title':'Junior Software Engineer','companyName':'Example',
            'location':'United States','descriptionText':'Build software using Python.',
            'applyUrl':'https://jobs.example.org/123'},
            {'title':'Missing application URL','companyName':'Example'}])
    monkeypatch.setattr(discovery.httpx,'Client',lambda **kwargs:original_client(transport=httpx.MockTransport(handler),**kwargs))
    monkeypatch.setattr(discovery,'secret',lambda name:None)
    settings=Settings(sources=[{'provider':'apify','board':'dataset123','company':'LinkedIn'}])
    assert discovery.discover(settings)==1
    assert discovery.discover(settings)==1
    assert len(db.jobs())==1
    assert db.jobs()[0]['company']=='Example'


def test_completed_run_is_reused_until_dataset_committed(tmp_path,monkeypatch):
    monkeypatch.setattr(apify_source,'DATA',tmp_path)
    monkeypatch.setattr(apify_source,'secret',lambda name:'token')
    calls=[]
    def handler(request):
        calls.append(request.method)
        return httpx.Response(200,json={'data':{'id':'run123','status':'SUCCEEDED','defaultDatasetId':'dataset123'}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        dataset,path=apify_source.dataset(client,{'board':'owner~actor'})
        assert dataset=='dataset123'
        assert apify_source.dataset(client,{'board':'owner~actor'})[0]=='dataset123'
        assert calls.count('POST')==1
        apify_source.consumed(path)
