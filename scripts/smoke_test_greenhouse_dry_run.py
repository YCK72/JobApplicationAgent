from __future__ import annotations

import sys

from app.applications.adapters.detector import (
    ATSDetector,
    ATSProvider,
)
from app.applications.answer_service import (
    build_application_answer_resolver,
)
from app.applications.composition import (
    build_application_adapter_registry,
)
from app.applications.dry_run import (
    ApplicationDryRunReporter,
    DryRunFieldStatus,
)
from app.applications.form_analyzer import (
    ApplicationFormAnalyzer,
)
from app.applications.form_plan import (
    ApplicationFormPlanner,
)


def main() -> int:
    if len(sys.argv) != 2:
        print(
            "Usage: python -m "
            "scripts.smoke_test_greenhouse_dry_run "
            "<greenhouse-job-url>"
        )
        return 2

    job_url = sys.argv[1].strip()

    if not job_url:
        print("ERROR: Job URL must not be empty.")
        return 2

    provider = ATSDetector.detect(job_url)

    print("=" * 72)
    print("LIVE GREENHOUSE APPLICATION DRY RUN")
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
        return 1

    print(
        "SAFETY MODE: inspection and deterministic planning only."
    )
    print(
        "Browser form mutation components are not instantiated."
    )
    print()

    registry = build_application_adapter_registry()

    adapter = registry.create(
        provider=provider,
        job_url=job_url,
    )

    print(
        "Launching Brave for read-only Greenhouse inspection..."
    )
    print()

    try:
        form = adapter.inspect()
    except Exception as exc:
        print()
        print("INSPECTION FAILED")
        print(f"{type(exc).__name__}: {exc}")
        return 1

    print("Read-only inspection complete.")
    print(f"Normalized fields: {len(form.fields)}")
    print()

    try:
        answer_resolver = build_application_answer_resolver()
    except Exception as exc:
        print("ANSWER CONFIGURATION FAILED")
        print(f"{type(exc).__name__}: {exc}")
        return 1

    analyzer = ApplicationFormAnalyzer(
        answer_resolver=answer_resolver,
    )

    planner = ApplicationFormPlanner()

    analysis = analyzer.analyze(form)
    plan = planner.build_plan(analysis)

    reporter = ApplicationDryRunReporter()

    report = reporter.build_report(
        form=form,
        plan=plan,
    )

    print("=" * 72)
    print("REDACTED DRY-RUN REPORT")
    print("=" * 72)
    print()
    print(f"Provider:          {report.provider}")
    print(f"Job URL:           {report.job_url}")
    print(f"Form status:       {plan.status.value}")
    print(
        "Execution status:  "
        f"{report.execution_status.value}"
    )
    print(
        "Would execute:     "
        f"{report.would_execute}"
    )
    print(
        "May submit:        "
        f"{report.may_submit}"
    )
    print(
        "Would-fill fields: "
        f"{report.would_fill_count}"
    )
    print()

    for index, result in enumerate(
        report.fields,
        start=1,
    ):
        print("-" * 72)
        print(f"Field #{index}")
        print(f"ID:       {result.field_id}")
        print(f"Label:    {result.label}")
        print(f"Type:     {result.field_type}")
        print(f"Required: {result.required}")
        print(f"Decision: {result.status.value}")
        print(f"Reason:   {result.reason}")

        if result.status == DryRunFieldStatus.WOULD_FILL:
            print(
                "Value:    [REDACTED VERIFIED VALUE]"
            )
        else:
            print("Value:    [NOT USED]")

    print()
    print("=" * 72)
    print("DRY RUN COMPLETE")
    print("=" * 72)
    print()
    print(
        "No candidate answer values were printed."
    )
    print(
        "No fields were filled."
    )
    print(
        "No dropdowns were selected."
    )
    print(
        "No files were uploaded."
    )
    print(
        "No buttons were clicked."
    )
    print(
        "No application was submitted."
    )
    print()
    print(
        "This report is diagnostic only. Per-field WOULD_FILL "
        "results do not override whole-form execution blocking."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())