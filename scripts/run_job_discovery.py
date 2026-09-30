"""Discover jobs into persistent SQLite storage and refresh the Excel tracker."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from dotenv import load_dotenv

from app.discovery.production import (
    DEFAULT_DATABASE_PATH,
    DEFAULT_EXPORT_PATH,
    PersistentDiscoveryRunner,
    build_persistent_discovery_runner,
)
from app.utils.config import ConfigError


RunnerBuilder = Callable[..., PersistentDiscoveryRunner]


def bounded_limit(value: str) -> int:
    try:
        limit = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "limit must be an integer from 1 to 20"
        ) from None
    if not 1 <= limit <= 20:
        raise argparse.ArgumentTypeError(
            "limit must be an integer from 1 to 20"
        )
    return limit


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--query",
        required=True,
        help="Role and location to search",
    )
    parser.add_argument(
        "--limit",
        type=bounded_limit,
        default=3,
        help="Maximum LinkedIn pages to fetch (1-20)",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help="Persistent SQLite database path",
    )
    parser.add_argument(
        "--export",
        type=Path,
        default=DEFAULT_EXPORT_PATH,
        help="Excel tracker output path",
    )
    return parser


def main(
    argv: list[str] | None = None,
    *,
    runner_builder: RunnerBuilder = build_persistent_discovery_runner,
) -> int:
    args = build_parser().parse_args(argv)
    load_dotenv(PROJECT_ROOT / ".env", override=False)

    try:
        runner = runner_builder(
            query=args.query,
            max_results=args.limit,
            database_path=args.database,
            export_path=args.export,
        )
        result = runner.run()
    except (ConfigError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "processed": result.processed_count,
                "stored_jobs": result.stored_job_count,
                "expired_jobs_filtered": result.expired_job_count,
                "expired_job_ids": list(result.expired_job_ids),
                "outcomes": result.outcome_counts,
                "errors": result.discovery_result.errors,
                "excel": str(result.export_path),
                "application_workflow_ran": False,
            },
            indent=2,
        )
    )

    return 1 if result.error_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
