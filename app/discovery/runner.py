from __future__ import annotations

from dataclasses import dataclass, field

from app.discovery.base import JobSource
from app.jobs.pipeline import JobPipeline, PipelineResult


@dataclass
class DiscoveryRunResult:
    """
    Structured result from running one or more discovery sources.

    The runner records successful pipeline results and source-level errors
    without taking over any responsibilities from JobPipeline.
    """

    pipeline_results: list[PipelineResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def discovered_count(self) -> int:
        """
        Number of jobs that successfully reached JobPipeline.
        """

        return len(self.pipeline_results)

    @property
    def error_count(self) -> int:
        """
        Number of source-level failures encountered during discovery.
        """

        return len(self.errors)


class DiscoveryRunner:
    """
    Coordinates job discovery sources with the existing JobPipeline.

    Responsibilities:

        1. Ask each JobSource to discover and normalize jobs.
        2. Send each normalized Job through JobPipeline.
        3. Collect PipelineResult objects.
        4. Record source-level discovery failures.

    This class does NOT classify, filter, score, deduplicate, persist,
    select resumes, open browsers, fill forms, or submit applications.
    """

    def __init__(
        self,
        *,
        pipeline: JobPipeline,
        sources: list[JobSource],
    ) -> None:
        self.pipeline = pipeline
        self.sources = list(sources)

    def run(self) -> DiscoveryRunResult:
        """
        Run all configured discovery sources.

        A failure in one source does not prevent later sources from running.
        Jobs successfully discovered by a source are processed individually
        through the existing JobPipeline.
        """

        result = DiscoveryRunResult()

        for source in self.sources:
            try:
                jobs = source.discover_jobs()
            except Exception as exc:
                result.errors.append(
                    f"{source.source_name}: discovery failed: {exc}"
                )
                continue

            for job in jobs:
                pipeline_result = self.pipeline.process(job)
                result.pipeline_results.append(pipeline_result)

        return result