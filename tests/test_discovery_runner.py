from __future__ import annotations

from app.discovery.base import JobSource, RawJobPosting
from app.discovery.runner import DiscoveryRunResult, DiscoveryRunner
from app.jobs.models import Job
from app.jobs.pipeline import PipelineOutcome, PipelineResult


class FakeJobSource(JobSource):
    """
    Deterministic discovery source used to test DiscoveryRunner.
    """

    def __init__(
        self,
        *,
        source_name: str = "fake_source",
        company: str = "Example Company",
        title: str = "Software Engineer I",
        url: str = "https://example.com/jobs/123",
    ) -> None:
        self._source_name = source_name
        self.company = company
        self.title = title
        self.url = url

    @property
    def source_name(self) -> str:
        return self._source_name

    def discover(self) -> list[RawJobPosting]:
        return [
            RawJobPosting(
                source=self.source_name,
                company=self.company,
                title=self.title,
                location="Seattle, WA",
                url=self.url,
                description="Build Python backend services.",
                external_job_id="123",
                date_posted="2026-09-25",
            )
        ]

    def normalize(self, raw_job: RawJobPosting) -> Job:
        return Job(
            company=raw_job.company,
            title=raw_job.title,
            location=raw_job.location,
            url=raw_job.url,
            source=raw_job.source,
            description=raw_job.description,
            external_job_id=raw_job.external_job_id,
            date_posted=raw_job.date_posted,
        )


class BrokenJobSource(JobSource):
    """
    Source that intentionally fails during discovery.
    """

    @property
    def source_name(self) -> str:
        return "broken_source"

    def discover(self) -> list[RawJobPosting]:
        raise RuntimeError("simulated discovery failure")

    def normalize(self, raw_job: RawJobPosting) -> Job:
        raise AssertionError(
            "normalize should never be called when discovery fails"
        )


class FakePipeline:
    """
    Small pipeline double that records every Job it receives.
    """

    def __init__(self) -> None:
        self.processed_jobs: list[Job] = []

    def process(self, job: Job) -> PipelineResult:
        self.processed_jobs.append(job)

        return PipelineResult(
            job=job,
            outcome=PipelineOutcome.AUTO_READY,
            reason="Fake pipeline processed job.",
            job_id=len(self.processed_jobs),
        )


class BrokenPipeline:
    """
    Pipeline double that intentionally fails.

    DiscoveryRunner must not hide internal pipeline failures.
    """

    def process(self, job: Job) -> PipelineResult:
        raise RuntimeError("simulated pipeline failure")


def test_discovery_run_result_defaults_are_empty():
    result = DiscoveryRunResult()

    assert result.pipeline_results == []
    assert result.errors == []
    assert result.discovered_count == 0
    assert result.error_count == 0


def test_runner_processes_discovered_job():
    pipeline = FakePipeline()
    source = FakeJobSource()

    runner = DiscoveryRunner(
        pipeline=pipeline,
        sources=[source],
    )

    result = runner.run()

    assert len(pipeline.processed_jobs) == 1
    assert len(result.pipeline_results) == 1
    assert result.discovered_count == 1
    assert result.error_count == 0

    processed_job = pipeline.processed_jobs[0]

    assert processed_job.company == "Example Company"
    assert processed_job.title == "Software Engineer I"
    assert processed_job.source == "fake_source"


def test_runner_returns_pipeline_result():
    pipeline = FakePipeline()
    source = FakeJobSource()

    runner = DiscoveryRunner(
        pipeline=pipeline,
        sources=[source],
    )

    result = runner.run()

    pipeline_result = result.pipeline_results[0]

    assert pipeline_result.outcome == PipelineOutcome.AUTO_READY
    assert pipeline_result.job_id == 1
    assert pipeline_result.reason == "Fake pipeline processed job."


def test_runner_processes_multiple_sources():
    pipeline = FakePipeline()

    first_source = FakeJobSource(
        source_name="source_one",
        company="Company One",
        url="https://example.com/jobs/1",
    )

    second_source = FakeJobSource(
        source_name="source_two",
        company="Company Two",
        url="https://example.com/jobs/2",
    )

    runner = DiscoveryRunner(
        pipeline=pipeline,
        sources=[
            first_source,
            second_source,
        ],
    )

    result = runner.run()

    assert result.discovered_count == 2
    assert result.error_count == 0

    assert len(pipeline.processed_jobs) == 2
    assert pipeline.processed_jobs[0].company == "Company One"
    assert pipeline.processed_jobs[1].company == "Company Two"


def test_broken_source_does_not_stop_later_source():
    pipeline = FakePipeline()

    runner = DiscoveryRunner(
        pipeline=pipeline,
        sources=[
            BrokenJobSource(),
            FakeJobSource(),
        ],
    )

    result = runner.run()

    assert result.discovered_count == 1
    assert result.error_count == 1

    assert len(pipeline.processed_jobs) == 1
    assert pipeline.processed_jobs[0].company == "Example Company"

    assert (
        result.errors[0]
        == "broken_source: discovery failed: simulated discovery failure"
    )


def test_empty_source_list_returns_empty_result():
    pipeline = FakePipeline()

    runner = DiscoveryRunner(
        pipeline=pipeline,
        sources=[],
    )

    result = runner.run()

    assert result.pipeline_results == []
    assert result.errors == []
    assert result.discovered_count == 0
    assert result.error_count == 0
    assert pipeline.processed_jobs == []


def test_pipeline_failure_is_not_silently_swallowed():
    runner = DiscoveryRunner(
        pipeline=BrokenPipeline(),
        sources=[FakeJobSource()],
    )

    try:
        runner.run()
    except RuntimeError as exc:
        assert str(exc) == "simulated pipeline failure"
    else:
        raise AssertionError(
            "DiscoveryRunner incorrectly swallowed a pipeline failure."
        )