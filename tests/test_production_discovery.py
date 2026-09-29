from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.discovery.production import (
    PersistentDiscoveryResult,
    PersistentDiscoveryRunner,
    build_persistent_discovery_runner,
)
from app.discovery.runner import DiscoveryRunResult
from app.jobs.models import Job
from app.jobs.pipeline import PipelineOutcome, PipelineResult
from scripts.run_job_discovery import main


def pipeline_result(outcome: PipelineOutcome) -> PipelineResult:
    return PipelineResult(
        job=Job(
            company="Example",
            title="Software Engineer I",
            location="Seattle, WA",
            url="https://example.com/jobs/1",
            source="test",
        ),
        outcome=outcome,
        reason="Test result",
        job_id=None if outcome == PipelineOutcome.DUPLICATE else 1,
    )


def test_persistent_runner_discovers_then_regenerates_tracker(
    tmp_path: Path,
) -> None:
    discovery_result = DiscoveryRunResult(
        pipeline_results=[
            pipeline_result(PipelineOutcome.AUTO_READY),
            pipeline_result(PipelineOutcome.MANUAL_REVIEW),
        ]
    )
    discovery_runner = MagicMock()
    discovery_runner.run.return_value = discovery_result
    database = MagicMock()
    database.get_all_jobs.return_value = [MagicMock(), MagicMock()]
    tracker = MagicMock()
    export_path = tmp_path / "tracker.xlsx"
    tracker.generate.return_value = export_path

    result = PersistentDiscoveryRunner(
        discovery_runner=discovery_runner,
        database=database,
        tracker=tracker,
    ).run()

    assert result.discovery_result is discovery_result
    assert result.export_path == export_path
    assert result.stored_job_count == 2
    assert result.outcome_counts == {
        "AUTO_READY": 1,
        "MANUAL_REVIEW": 1,
    }
    discovery_runner.run.assert_called_once_with()
    tracker.generate.assert_called_once_with()


def test_tracker_is_refreshed_after_source_level_failure(
    tmp_path: Path,
) -> None:
    discovery_runner = MagicMock()
    discovery_runner.run.return_value = DiscoveryRunResult(
        errors=["linkedin_composio: discovery failed: unavailable"]
    )
    database = MagicMock()
    database.get_all_jobs.return_value = []
    tracker = MagicMock()
    tracker.generate.return_value = tmp_path / "tracker.xlsx"

    result = PersistentDiscoveryRunner(
        discovery_runner=discovery_runner,
        database=database,
        tracker=tracker,
    ).run()

    assert result.error_count == 1
    assert result.stored_job_count == 0
    tracker.generate.assert_called_once_with()


def test_production_builder_persists_and_exports_discovered_jobs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from app.discovery import production

    url = "https://www.linkedin.com/jobs/view/example-role-12345"
    client = MagicMock()
    client.search.return_value = {
        "citations": [{
            "url": url,
            "title": (
                "Example hiring Software Engineer I in Seattle, WA "
                "| LinkedIn"
            ),
        }]
    }
    client.fetch.return_value = {
        "results": [{
            "url": url,
            "title": (
                "Example hiring Software Engineer I in Seattle, WA "
                "| LinkedIn"
            ),
            "text": (
                "Example hiring Software Engineer I in Seattle, WA "
                "| LinkedIn\n\n# Software Engineer I\n\n"
                "Example Seattle, WA\n\nBuild Python services."
            ),
        }]
    }

    def fake_pipeline_builder(*, database):
        class PersistingPipeline:
            def process(self, job):
                job_id = database.add_job(job)
                return PipelineResult(
                    job=job,
                    outcome=PipelineOutcome.MANUAL_REVIEW,
                    reason="Test persistence",
                    job_id=job_id,
                )

        return PersistingPipeline()

    monkeypatch.setattr(
        production,
        "build_job_pipeline",
        fake_pipeline_builder,
    )
    database_path = tmp_path / "jobs.db"
    export_path = tmp_path / "tracker.xlsx"

    result = build_persistent_discovery_runner(
        query="software engineer Seattle",
        max_results=1,
        database_path=database_path,
        export_path=export_path,
        client=client,
    ).run()

    assert result.processed_count == 1
    assert result.stored_job_count == 1
    assert result.outcome_counts == {"MANUAL_REVIEW": 1}
    assert database_path.is_file()
    assert export_path.is_file()


def test_pipeline_failure_stops_before_tracker_generation() -> None:
    discovery_runner = MagicMock()
    discovery_runner.run.side_effect = RuntimeError("pipeline failed")
    tracker = MagicMock()

    with pytest.raises(RuntimeError, match="pipeline failed"):
        PersistentDiscoveryRunner(
            discovery_runner=discovery_runner,
            database=MagicMock(),
            tracker=tracker,
        ).run()

    tracker.generate.assert_not_called()


def test_missing_api_key_does_not_create_database(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("COMPOSIO_API_KEY", raising=False)
    database_path = tmp_path / "jobs.db"

    with pytest.raises(ValueError, match="COMPOSIO_API_KEY"):
        build_persistent_discovery_runner(
            query="software engineer",
            database_path=database_path,
            export_path=tmp_path / "tracker.xlsx",
        )

    assert not database_path.exists()


def test_cli_prints_summary_and_never_runs_application_workflow(
    tmp_path: Path,
    capsys,
) -> None:
    export_path = tmp_path / "tracker.xlsx"
    result = PersistentDiscoveryResult(
        discovery_result=DiscoveryRunResult(
            pipeline_results=[
                pipeline_result(PipelineOutcome.AUTO_READY),
            ]
        ),
        export_path=export_path,
        stored_job_count=1,
    )
    builder = MagicMock(
        return_value=SimpleNamespace(run=MagicMock(return_value=result))
    )

    exit_code = main(
        [
            "--query",
            "entry level software engineer Seattle",
            "--limit",
            "3",
            "--database",
            str(tmp_path / "jobs.db"),
            "--export",
            str(export_path),
        ],
        runner_builder=builder,
    )

    assert exit_code == 0
    assert '"processed": 1' in capsys.readouterr().out
    builder.assert_called_once_with(
        query="entry level software engineer Seattle",
        max_results=3,
        database_path=tmp_path / "jobs.db",
        export_path=export_path,
    )


def test_cli_returns_failure_when_a_source_fails(
    tmp_path: Path,
    capsys,
) -> None:
    result = PersistentDiscoveryResult(
        discovery_result=DiscoveryRunResult(errors=["safe error"]),
        export_path=tmp_path / "tracker.xlsx",
        stored_job_count=4,
    )
    builder = MagicMock(
        return_value=SimpleNamespace(run=MagicMock(return_value=result))
    )

    exit_code = main(
        ["--query", "software engineer", "--limit", "2"],
        runner_builder=builder,
    )

    assert exit_code == 1
    assert '"errors": [\n    "safe error"\n  ]' in capsys.readouterr().out


@pytest.mark.parametrize("limit", ["0", "21"])
def test_cli_rejects_unbounded_limits(limit: str) -> None:
    with pytest.raises(SystemExit):
        main(
            ["--query", "software engineer", "--limit", limit],
            runner_builder=MagicMock(),
        )


def test_cli_reports_configuration_error_without_traceback(
    capsys,
) -> None:
    builder = MagicMock(side_effect=ValueError("missing configuration"))

    exit_code = main(
        ["--query", "software engineer"],
        runner_builder=builder,
    )

    assert exit_code == 2
    assert capsys.readouterr().err.strip() == "missing configuration"
