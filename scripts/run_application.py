"""Preview or launch one exact persisted job through the controlled workflow."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app.applications.composition import (
    DEFAULT_APPLICATION_ANSWERS_PATH,
    DEFAULT_APPLICATION_DATABASE_PATH,
    DEFAULT_APPLICATION_EXPORT_PATH,
    build_single_job_application_launcher,
)
from app.applications.single_job import (
    SingleJobApplicationLauncher,
    SingleJobLaunchStatus,
)


LauncherBuilder = Callable[..., SingleJobApplicationLauncher]


def _url_text(value: object) -> str | None:
    if isinstance(value, str):
        return value
    encoded_string = getattr(value, "encoded_string", None)
    if callable(encoded_string) and type(value).__module__.startswith(
        ("pydantic", "pydantic_core")
    ):
        return encoded_string()
    return None


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
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--job-id", type=positive_job_id)
    selection.add_argument(
        "--list-eligible",
        action="store_true",
        help="List persisted jobs eligible for exact-ID launch and exit",
    )
    parser.add_argument(
        "--allow-external",
        action="store_true",
        help=(
            "Explicitly authorize browser inspection and field mutation for "
            "the exact selected external job. Submission remains prohibited."
        ),
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
    parser.add_argument(
        "--answers",
        type=Path,
        default=DEFAULT_APPLICATION_ANSWERS_PATH,
    )
    return parser


def main(
    argv: list[str] | None = None,
    *,
    launcher_builder: LauncherBuilder = build_single_job_application_launcher,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.list_eligible and args.allow_external:
        parser.error("--allow-external requires --job-id")

    try:
        launcher = launcher_builder(
            database_path=args.database,
            export_path=args.export,
            answer_config_path=args.answers,
        )
        if args.list_eligible:
            candidates = launcher.list_eligible()
            print(
                json.dumps(
                    {
                        "eligible_jobs": [
                            {
                                "job_id": candidate.job_id,
                                "company": candidate.job.company,
                                "title": candidate.job.title,
                                "location": candidate.job.location,
                                "fit_score": candidate.job.fit_score,
                                "status": candidate.job.status.value,
                                "source_url": _url_text(
                                    getattr(candidate.job, "url", None)
                                ),
                                "application_url": (
                                    _url_text(getattr(
                                        candidate.job,
                                        "application_url",
                                        None,
                                    ))
                                    or _url_text(getattr(
                                        candidate.job,
                                        "url",
                                        None,
                                    ))
                                ),
                            }
                            for candidate in candidates
                        ],
                        "application_workflow_ran": False,
                        "may_submit": False,
                    },
                    indent=2,
                )
            )
            return 0
        result = launcher.run(
            job_id=args.job_id,
            allow_external=args.allow_external,
        )
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    job = result.job
    payload = {
        "job_id": result.job_id,
        "status": result.status.value,
        "reason": result.reason,
        "completed_actions": result.completed_actions,
        "may_submit": result.may_submit,
        "job": (
            {
                "company": job.company,
                "title": job.title,
                "location": job.location,
                "source_url": _url_text(getattr(job, "url", None)),
                "application_url": _url_text(
                    getattr(job, "application_url", None)
                ),
                "fit_score": job.fit_score,
                "resume": (
                    Path(job.resume_used).name
                    if job.resume_used
                    else None
                ),
                "application_status": job.status.value,
            }
            if job is not None
            else None
        ),
        "excel": (
            str(result.export_path)
            if result.export_path is not None
            else None
        ),
    }
    print(json.dumps(payload, indent=2))

    return (
        0
        if result.status == SingleJobLaunchStatus.READY_FOR_REVIEW
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
