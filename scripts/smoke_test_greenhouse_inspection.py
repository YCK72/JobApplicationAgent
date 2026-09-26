from __future__ import annotations

import sys

from app.applications.adapters.detector import (
    ATSDetector,
    ATSProvider,
)
from app.applications.composition import (
    build_application_adapter_registry,
)


def main() -> int:
    if len(sys.argv) != 2:
        print(
            "Usage: python -m "
            "scripts.smoke_test_greenhouse_inspection "
            "<greenhouse-job-url>"
        )
        return 2

    job_url = sys.argv[1].strip()

    if not job_url:
        print("ERROR: Job URL must not be empty.")
        return 2

    provider = ATSDetector.detect(job_url)

    print("=" * 72)
    print("LIVE GREENHOUSE READ-ONLY INSPECTION")
    print("=" * 72)
    print()
    print(f"URL:      {job_url}")
    print(f"Provider: {provider.value}")
    print()

    if provider != ATSProvider.GREENHOUSE:
        print(
            "STOPPED: URL was not recognized as "
            "a supported Greenhouse job URL."
        )
        print()
        print(
            "Expected an individual job URL hosted on:"
        )
        print("  - boards.greenhouse.io")
        print("  - job-boards.greenhouse.io")
        return 1

    registry = build_application_adapter_registry()

    adapter = registry.create(
        provider=provider,
        job_url=job_url,
    )

    print(
        "Launching Brave in read-only inspection mode..."
    )
    print()

    try:
        form = adapter.inspect()
    except Exception as exc:
        print()
        print("INSPECTION FAILED")
        print(
            f"{type(exc).__name__}: {exc}"
        )
        return 1

    print()
    print("=" * 72)
    print("NORMALIZED APPLICATION FORM")
    print("=" * 72)
    print()
    print(f"Provider: {form.provider}")
    print(f"Job URL:  {form.job_url}")
    print(f"Fields:   {len(form.fields)}")
    print()

    for index, field in enumerate(
        form.fields,
        start=1,
    ):
        print("-" * 72)
        print(f"Field #{index}")
        print(f"ID:       {field.field_id}")
        print(f"Label:    {field.label}")
        print(f"Type:     {field.field_type.value}")
        print(f"Required: {field.required}")

        if field.options:
            print("Options:")

            for option in field.options:
                print(f"  - {option}")

        if field.current_value:
            print(
                "Current value: "
                f"{field.current_value!r}"
            )

    print()
    print("=" * 72)
    print("INSPECTION COMPLETE")
    print("=" * 72)
    print()
    print(
        "No fields were filled, no files were uploaded, "
        "and no form was submitted."
    )
    print(
        "The browser session was closed by the adapter."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())