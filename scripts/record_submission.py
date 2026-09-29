"""Record supplied post-review submission evidence for one persisted job."""
from __future__ import annotations

import argparse
from datetime import date, datetime
import json
from pathlib import Path
import sys
from typing import Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app.applications.composition import (
    DEFAULT_APPLICATION_DATABASE_PATH,
    DEFAULT_APPLICATION_EXPORT_PATH,
    build_submission_recording_runner,
)
from app.applications.submission_confirmation import (
    SubmissionConfirmationOutcome,
)
from app.applications.submission_recording import SubmissionRecordingRunner


RunnerBuilder = Callable[..., SubmissionRecordingRunner]


def positive_job_id(value: str) -> int:
    try:
        job_id = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "job ID must be a positive integer"
        ) from None
    if job_id <= 0:
        raise argparse.ArgumentTypeError(
            "job ID must be a positive integer"
        )
    return job_id


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-id", required=True, type=positive_job_id)
    parser.add_argument(
        "--submitted",
        action="store_true",
        help="Report that a human submission attempt occurred",
    )
    parser.add_argument(
        "--confirmed",
        action="store_true",
        help="Report independently confirmed success; requires --submitted",
    )
    parser.add_argument(
        "--evidence",
        help="Independent confirmation evidence or uncertainty note",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_APPLICATION_DATABASE_PATH,
    )
    parser.add_argument(
        "--export",
        type=Path,
        default=DEFAULT_APPLICATION_EXPORT_PATH,
    )
    return parser


def main(
    argv: list[str] | None = None,
    *,
    runner_builder: RunnerBuilder = build_submission_recording_runner,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.confirmed and not args.submitted:
        parser.error("--confirmed requires --submitted")
    if args.evidence is not None and not args.submitted:
        parser.error("--evidence requires --submitted")
    if args.confirmed and not (args.evidence and args.evidence.strip()):
        parser.error("--confirmed requires nonblank --evidence")

    try:
        runner = runner_builder(
            database_path=args.database,
            export_path=args.export,
        )
        result = runner.record(
            job_id=args.job_id,
            submitted=args.submitted,
            success_confirmed=args.confirmed,
            evidence=args.evidence,
        )
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    job = result.job
    date_applied = job.date_applied if job is not None else None
    if isinstance(date_applied, (date, datetime)):
        date_applied = date_applied.isoformat()
    elif date_applied is not None:
        date_applied = str(date_applied)

    print(
        json.dumps(
            {
                "job_id": result.job_id,
                "outcome": result.outcome.value,
                "reason": result.reason,
                "confirmed": result.confirmed,
                "may_submit": result.may_submit,
                "job": (
                    {
                        "company": job.company,
                        "title": job.title,
                        "application_status": job.status.value,
                        "date_applied": date_applied,
                    }
                    if job is not None
                    else None
                ),
                "excel": (
                    str(result.export_path)
                    if result.export_path is not None
                    else None
                ),
                "tracker_error": result.tracker_error,
                "browser_ran": False,
            },
            indent=2,
        )
    )

    if result.tracker_error is not None:
        return 2
    if result.outcome in {
        SubmissionConfirmationOutcome.CONFIRMED,
        SubmissionConfirmationOutcome.UNCONFIRMED,
        SubmissionConfirmationOutcome.NOT_SUBMITTED,
    }:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
