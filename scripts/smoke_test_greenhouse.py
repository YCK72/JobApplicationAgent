from __future__ import annotations

from app.discovery.greenhouse import (
    GreenhouseDiscoveryError,
    GreenhouseJobSource,
)


# Change these two values when testing another public
# Greenhouse board.
COMPANY = "SingleStore"
BOARD_TOKEN = "singlestore"

# We deliberately display only a small sample.
SAMPLE_SIZE = 5


def main() -> None:
    print("=" * 70)
    print("CONTROLLED GREENHOUSE LIVE DISCOVERY TEST")
    print("=" * 70)

    source = GreenhouseJobSource(
        company=COMPANY,
        board_token=BOARD_TOKEN,
    )

    print(f"Company:      {source.company}")
    print(f"Source:       {source.source_name}")
    print(f"Board token:  {source.board_token}")
    print(f"Endpoint:     {source.jobs_url}")
    print()

    print("Requesting public Greenhouse job data...")
    print()

    try:
        raw_jobs = source.discover()

    except GreenhouseDiscoveryError as exc:
        print("DISCOVERY FAILED")
        print(f"Reason: {exc}")
        return

    except Exception as exc:
        print("UNEXPECTED FAILURE")
        print(
            f"{type(exc).__name__}: {exc}"
        )
        raise

    print("Discovery successful.")
    print(f"Jobs returned: {len(raw_jobs)}")
    print()

    if not raw_jobs:
        print("The board returned zero jobs.")
        return

    sample = raw_jobs[:SAMPLE_SIZE]

    print(
        f"Displaying first {len(sample)} "
        "job(s) only:"
    )
    print()

    for index, raw_job in enumerate(
        sample,
        start=1,
    ):
        print("-" * 70)
        print(f"JOB {index}")
        print("-" * 70)

        print(f"Company:     {raw_job.company}")
        print(f"Title:       {raw_job.title}")
        print(f"Location:    {raw_job.location}")
        print(f"External ID: {raw_job.external_job_id}")
        print(f"Date posted: {raw_job.date_posted}")
        print(f"URL:         {raw_job.url}")
        print()

    print("=" * 70)
    print("SAFETY CHECK")
    print("=" * 70)

    print(
        "This script performed discovery only."
    )
    print(
        "No jobs were inserted into SQLite."
    )
    print(
        "No resumes were selected."
    )
    print(
        "No browser automation was started."
    )
    print(
        "No applications were submitted."
    )


if __name__ == "__main__":
    main()