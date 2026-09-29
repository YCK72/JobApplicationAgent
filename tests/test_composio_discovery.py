import json
from unittest.mock import MagicMock
from urllib.error import HTTPError, URLError

import pytest

from app.discovery.composio import (
    ComposioDiscoveryError, ComposioSearchClient, LinkedInComposioJobSource,
    canonical_linkedin_job_url,
)
from app.discovery.runner import DiscoveryRunner
from app.jobs.models import ApplicationStatus

URL = "https://www.linkedin.com/jobs/view/software-engineer-at-example-12345"
TITLE = "Example hiring Software Engineer in Seattle, WA | LinkedIn"
TEXT = "Example hiring Software Engineer in Seattle, WA | LinkedIn\n\n# Software Engineer\n\nExample Seattle, WA\n\nBuild Python services."


def client_with_page(**changes):
    page = {"url": URL, "title": TITLE, "text": TEXT}
    page.update(changes)
    client = MagicMock()
    client.search.return_value = {"citations": [{"url": URL, "title": TITLE}]}
    client.fetch.return_value = {"results": [page]}
    return client


def source(client=None, **kwargs):
    return LinkedInComposioJobSource(client=client or client_with_page(), query="software engineer Seattle", **kwargs)


def test_discovery_and_normalization_preserve_source_data():
    client = client_with_page()
    adapter = source(client)
    client.search.assert_not_called()
    raw = adapter.discover()[0]
    assert (raw.company, raw.title, raw.location) == ("Example", "Software Engineer", "Seattle, WA")
    assert raw.external_job_id == "12345"
    assert raw.url == "https://www.linkedin.com/jobs/view/12345"
    assert raw.description == TEXT
    assert raw.date_posted is None
    job = adapter.normalize(raw)
    assert job.status == ApplicationStatus.DISCOVERED
    assert job.resume_used is None
    assert job.source == "linkedin_composio"
    client.search.assert_called_once_with("site:linkedin.com/jobs/view software engineer Seattle")
    client.fetch.assert_called_once_with([URL])


@pytest.mark.parametrize("url", [
    "https://linkedin.com/jobs/search/?keywords=test", "https://evil.com/jobs/view/12345",
    "https://linkedin.com.evil.com/jobs/view/12345", "file:///jobs/view/12345",
    "https://user:pass@linkedin.com/jobs/view/12345", "https://linkedin.com:444/jobs/view/12345",
    "https://linkedin.com/jobs/view/not-a-job", None, "https://linkedin.com/jobs/view/123/extra",
])
def test_reject_non_detail_urls(url):
    assert canonical_linkedin_job_url(url) is None


@pytest.mark.parametrize("url", [URL + "?trackingId=abc#foo", "https://uk.linkedin.com/jobs/view/12345/", "http://linkedin.com/jobs/view/12345"])
def test_canonical_job_identity(url):
    assert canonical_linkedin_job_url(url) == "https://www.linkedin.com/jobs/view/12345"


def test_deduplicates_and_bounds_fetches():
    client = client_with_page()
    client.search.return_value = {"results": {"citations": [
        {"url": URL + "?trackingId=x"}, {"url": URL},
        {"url": "https://www.linkedin.com/jobs/view/99999"},
        {"url": "https://example.com/not-a-job"},
    ]}}
    assert len(source(client, max_results=1).discover()) == 1
    client.fetch.assert_called_once_with([URL])


@pytest.mark.parametrize("changes", [
    {"text": "Sign in to LinkedIn"}, {"title": "Software Engineer"},
    {"text": TEXT + "\nNo longer accepting applications"},
    {"text": TEXT.replace("# Software Engineer", "# Different Job")},
    {"url": "https://www.linkedin.com/jobs/view/99999"},
    {"text": None},
])
def test_incomplete_expired_or_mismatched_pages_are_skipped(changes):
    assert source(client_with_page(**changes)).discover() == []


def test_alternate_explicit_title_format():
    title = "Software Engineer at Example — Seattle, WA | LinkedIn Jobs"
    raw = source(client_with_page(title=title)).discover()[0]
    assert raw.company == "Example"
    assert raw.title == "Software Engineer"


def test_empty_search_does_not_fetch():
    client = client_with_page()
    client.search.return_value = {"citations": []}
    assert source(client).discover() == []
    client.fetch.assert_not_called()


@pytest.mark.parametrize("payload", [{}, {"citations": "bad"}, {"results": None}])
def test_invalid_search_shape_fails_visibly(payload):
    client = client_with_page()
    client.search.return_value = payload
    with pytest.raises(ComposioDiscoveryError):
        source(client).discover()


def test_fetch_status_failure_is_not_a_posting():
    client = client_with_page()
    client.fetch.return_value["statuses"] = [{"id": URL, "status": "error"}]
    assert source(client).discover() == []


def test_discovery_runner_uses_existing_pipeline():
    pipeline = MagicMock()
    result = DiscoveryRunner(pipeline=pipeline, sources=[source()]).run()
    assert result.discovered_count == 1 and result.error_count == 0
    assert pipeline.process.call_args.args[0].company == "Example"


@pytest.mark.parametrize("kwargs", [{"max_results": 0}, {"max_results": 21}, {"max_results": True}])
def test_result_limit_validation(kwargs):
    with pytest.raises(ValueError):
        source(**kwargs)


def test_query_validation():
    with pytest.raises(ValueError):
        LinkedInComposioJobSource(client=MagicMock(), query=" ")


class Response:
    def __init__(self, payload):
        self.body = json.dumps(payload).encode()
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def read(self, limit):
        return self.body


def test_rest_request_pins_version_and_uses_project_key():
    opener = MagicMock()
    opener.open.return_value = Response({"successful": True, "data": {"citations": []}})
    client = ComposioSearchClient(api_key="test-key", opener=opener)
    assert client.search("query") == {"citations": []}
    request = opener.open.call_args.args[0]
    assert request.full_url.endswith("/COMPOSIO_SEARCH_WEB")
    assert request.get_header("X-api-key") == "test-key"
    body = json.loads(request.data)
    assert body["version"] == "20260903_00"
    assert body["arguments"] == {"query": "query"}
    assert opener.open.call_args.kwargs["timeout"] == 30


def test_fetch_request_is_bounded_text_only():
    opener = MagicMock()
    opener.open.return_value = Response({"successful": True, "data": {"results": []}})
    ComposioSearchClient(api_key="test-key", opener=opener).fetch([URL])
    body = json.loads(opener.open.call_args.args[0].data)
    assert body["arguments"] == {"urls": [URL], "text": True, "max_characters": 20000}


@pytest.mark.parametrize("payload", [[], {}, {"successful": False, "error": "SECRET"}, {"successful": True, "data": []}])
def test_bad_api_responses_are_sanitized(payload):
    opener = MagicMock()
    opener.open.return_value = Response(payload)
    with pytest.raises(ComposioDiscoveryError) as error:
        ComposioSearchClient(api_key="SECRET", opener=opener).search("query")
    assert "SECRET" not in str(error.value)


@pytest.mark.parametrize("error", [URLError("SECRET"), TimeoutError("SECRET"), HTTPError("https://example.com", 401, "SECRET", {}, None)])
def test_transport_errors_are_sanitized(error):
    opener = MagicMock()
    opener.open.side_effect = error
    with pytest.raises(ComposioDiscoveryError) as caught:
        ComposioSearchClient(api_key="SECRET", opener=opener).search("query")
    assert "SECRET" not in str(caught.value)


def test_missing_key_is_actionable(monkeypatch):
    monkeypatch.delenv("COMPOSIO_API_KEY", raising=False)
    with pytest.raises(ValueError, match="COMPOSIO_API_KEY"):
        ComposioSearchClient.from_environment()


def test_missing_location_remains_missing():
    client = client_with_page(title="Example hiring Software Engineer | LinkedIn")
    assert source(client).discover()[0].location is None


def test_organic_results_fallback():
    client = client_with_page()
    client.search.return_value = {"results": {"organic_results": [{"link": URL}]}}
    assert len(source(client).discover()) == 1


def test_generated_answer_is_never_used_as_job_data():
    client = client_with_page()
    client.search.return_value = {"answer": TITLE, "citations": []}
    assert source(client).discover() == []
    client.fetch.assert_not_called()


def test_malformed_fetch_fails_visibly():
    client = client_with_page()
    client.fetch.return_value = {"results": "unexpected"}
    with pytest.raises(ComposioDiscoveryError):
        source(client).discover()


@pytest.mark.parametrize("body", [b"not JSON", b"\xff", b"x" * 2_000_001], ids=["invalid-json", "invalid-utf8", "too-large"])
def test_invalid_or_oversized_response(body):
    opener = MagicMock()
    response = Response({})
    response.body = body
    opener.open.return_value = response
    with pytest.raises(ComposioDiscoveryError):
        ComposioSearchClient(api_key="test-key", opener=opener).search("query")


def test_existing_pipeline_persists_and_deduplicates(tmp_path):
    from scripts.smoke_test_live_discovery_pipeline import build_pipeline
    from app.tracking.database import JobDatabase
    from app.jobs.pipeline import PipelineOutcome

    database = JobDatabase(tmp_path / "composio.db")
    runner = DiscoveryRunner(pipeline=build_pipeline(database), sources=[source()])
    first = runner.run()
    second = runner.run()
    assert first.discovered_count == 1 and not first.errors
    assert second.pipeline_results[0].outcome == PipelineOutcome.DUPLICATE
    assert len(database.get_all_jobs()) == 1
    assert first.pipeline_results[0].job.status != ApplicationStatus.APPLIED
