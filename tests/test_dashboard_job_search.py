from pathlib import Path
import json
from threading import Thread
from unittest.mock import MagicMock
from urllib.request import Request, urlopen

import pytest

from app.dashboard.job_search import DashboardJobSearchService
from app.discovery.production import PersistentDiscoveryResult
from app.discovery.runner import DiscoveryRunResult
from app.jobs.models import Job
from app.jobs.pipeline import PipelineOutcome, PipelineResult
from app.dashboard.server import create_dashboard_server


def result(outcome: PipelineOutcome, job_id: int | None) -> PipelineResult:
    return PipelineResult(
        job=Job(
            company="Example",
            title="Software Engineer I",
            location="Seattle, WA",
            url=f"https://example.com/jobs/{job_id or 0}",
            source="test",
        ),
        outcome=outcome,
        reason="test",
        job_id=job_id,
    )


def test_search_returns_only_auto_ready_ids(tmp_path: Path) -> None:
    persistent = PersistentDiscoveryResult(
        discovery_result=DiscoveryRunResult(
            pipeline_results=[
                result(PipelineOutcome.AUTO_READY, 7),
                result(PipelineOutcome.MANUAL_REVIEW, 8),
                result(PipelineOutcome.FILTERED_OUT, 9),
            ],
            errors=["one source warning"],
        ),
        export_path=tmp_path / "tracker.xlsx",
        stored_job_count=9,
        expired_job_ids=(2,),
    )
    runner = MagicMock()
    runner.run.return_value = persistent
    builder = MagicMock(return_value=runner)
    service = DashboardJobSearchService(runner_builder=builder)

    summary = service.search(query="  software   engineer Seattle ", limit=3)

    assert summary.as_dict() == {
        "query": "software engineer Seattle",
        "processed": 3,
        "stored_jobs": 9,
        "expired_jobs": 1,
        "errors": ["one source warning"],
        "outcomes": {
            "AUTO_READY": 1,
            "FILTERED_OUT": 1,
            "MANUAL_REVIEW": 1,
        },
        "eligible_job_ids": [7],
    }
    builder.assert_called_once_with("software engineer Seattle", 3)


@pytest.mark.parametrize(
    ("query", "limit"),
    [("", 3), ("ab", 3), ("x" * 201, 3), ("Seattle", 0), ("Seattle", 11)],
)
def test_search_rejects_invalid_or_unbounded_input(query: str, limit: int) -> None:
    service = DashboardJobSearchService(runner_builder=MagicMock())

    with pytest.raises(ValueError):
        service.search(query=query, limit=limit)


def test_dashboard_search_api_returns_bounded_eligible_ids() -> None:
    service = MagicMock()
    service.search.return_value.as_dict.return_value = {
        "query": "software engineer Seattle",
        "processed": 1,
        "stored_jobs": 4,
        "expired_jobs": 0,
        "errors": [],
        "outcomes": {"AUTO_READY": 1},
        "eligible_job_ids": [12],
    }
    server = create_dashboard_server(
        reader=MagicMock(),
        host="127.0.0.1",
        port=0,
        job_search_service=service,
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = Request(
            f"http://127.0.0.1:{server.server_port}/api/job-search",
            data=json.dumps({
                "query": "software engineer Seattle",
                "limit": 3,
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            payload = json.load(response)
            assert response.status == 200
        assert payload["eligible_job_ids"] == [12]
        service.search.assert_called_once_with(
            query="software engineer Seattle",
            limit=3,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
