"""Run bounded Composio discovery through the pipeline in temporary storage."""
from __future__ import annotations

import argparse
import gc
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

from app.discovery.composio import (
    ComposioSearchClient, LinkedInComposioJobSource,
)
from app.discovery.runner import DiscoveryRunner
from app.tracking.database import JobDatabase
from scripts.smoke_test_live_discovery_pipeline import build_pipeline


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True, help="Role and location to search")
    parser.add_argument("--limit", type=int, default=3, help="Maximum pages to fetch (1-20)")
    args = parser.parse_args()
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    try:
        source = LinkedInComposioJobSource(
            client=ComposioSearchClient.from_environment(),
            query=args.query, max_results=args.limit,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    with TemporaryDirectory(prefix="jaa-composio-smoke-") as directory:
        try:
            database = JobDatabase(Path(directory) / "jobs.db")
            result = DiscoveryRunner(pipeline=build_pipeline(database), sources=[source]).run()
            print(json.dumps({
                "candidates": source.last_candidate_count,
                "skipped_pages": source.last_skipped_count,
                "processed": result.discovered_count,
                "errors": result.errors,
                "jobs": [{"company": item.job.company, "title": item.job.title,
                          "url": str(item.job.url), "outcome": item.outcome.value}
                         for item in result.pipeline_results],
            }, indent=2))
            if result.errors:
                return 1
            if not result.pipeline_results:
                print("No usable postings returned; live discovery is inconclusive.", file=sys.stderr)
                return 3
        finally:
            # Existing JobDatabase connections are transaction contexts, not
            # closing contexts. Collect released handles before Windows deletes
            # this smoke-only temporary database.
            gc.collect()
    print("Discovery-only smoke passed. Temporary database removed; no application workflow ran.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
