from __future__ import annotations

from pathlib import Path

from app.applications.browser_form_executor import (
    BrowserExecutionStatus,
    BrowserFormExecutor,
)
from app.applications.execution_guard import (
    ExternalExecutionGuard,
)
from app.applications.form_executor import (
    AuthorizedFieldAction,
    ExecutionPlanStatus,
    FormExecutionPlan,
)
from app.applications.form_models import (
    FormField,
    FormFieldType,
)
from app.browser.manager import BrowserSession
from app.browser.playwright_form_writer import (
    PlaywrightFieldWriter,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]

FIXTURE_PATH = (
    PROJECT_ROOT
    / "tests"
    / "fixtures"
    / "safe_application_form.html"
)


def make_field(
    field_id: str,
    label: str,
    field_type: FormFieldType,
) -> FormField:
    return FormField(
        field_id=field_id,
        label=label,
        field_type=field_type,
    )


def main() -> None:
    if not FIXTURE_PATH.is_file():
        raise RuntimeError(
            f"Fixture does not exist: {FIXTURE_PATH}"
        )

    fixture_url = FIXTURE_PATH.resolve().as_uri()

    guard = ExternalExecutionGuard(
        allowed_local_fixture=FIXTURE_PATH,
    )

    target_authorization = guard.authorize(
        fixture_url
    )

    if not target_authorization.may_mutate:
        raise RuntimeError(
            "Local fixture was not authorized: "
            f"{target_authorization.reason}"
        )

    if target_authorization.may_submit:
        raise RuntimeError(
            "Target authorization unexpectedly allowed submission."
        )

    fields = (
        make_field(
            "first_name",
            "First Name",
            FormFieldType.TEXT,
        ),
        make_field(
            "email",
            "Email",
            FormFieldType.EMAIL,
        ),
        make_field(
            "phone",
            "Phone",
            FormFieldType.PHONE,
        ),
        make_field(
            "short_answer",
            "Short Answer",
            FormFieldType.TEXTAREA,
        ),
    )

    values = (
        "Test",
        "test@example.com",
        "555-0100",
        "Controlled local smoke test.",
    )

    actions = tuple(
        AuthorizedFieldAction(
            field=field,
            value=value,
        )
        for field, value in zip(
            fields,
            values,
            strict=True,
        )
    )

    plan = FormExecutionPlan(
        actions=actions,
        status=ExecutionPlanStatus.AUTHORIZED,
        reason="Controlled local browser smoke test.",
    )

    with BrowserSession(headless=True) as session:
        page = session.navigate(fixture_url)

        writer = PlaywrightFieldWriter(page)
        executor = BrowserFormExecutor(writer)

        result = executor.execute(
            plan,
            target_authorization=target_authorization,
        )

        if result.status != BrowserExecutionStatus.COMPLETED:
            raise RuntimeError(
                f"Execution failed: {result.reason}"
            )

        if result.completed_actions != 4:
            raise RuntimeError(
                "Expected exactly four completed actions."
            )

        if result.may_submit:
            raise RuntimeError(
                "Execution unexpectedly allowed submission."
            )

        actual_values = (
            page.locator("#first_name").input_value(),
            page.locator("#email").input_value(),
            page.locator("#phone").input_value(),
            page.locator("#short_answer").input_value(),
        )

        if actual_values != values:
            raise RuntimeError(
                "Written values do not match expected values."
            )

        country_value = page.locator(
            "#country"
        ).input_value()

        if country_value != "":
            raise RuntimeError(
                "Country select was unexpectedly modified."
            )

        resume_value = page.locator(
            "#resume"
        ).input_value()

        if resume_value != "":
            raise RuntimeError(
                "Resume input was unexpectedly modified."
            )

        submission_count = page.evaluate(
            "() => window.testSubmissionCount"
        )

        if submission_count != 0:
            raise RuntimeError(
                "Form submission was unexpectedly triggered."
            )

        print("Local Brave form-fill smoke test PASSED")
        print(
            f"Completed actions: {result.completed_actions}"
        )
        print(
            f"Submission allowed: {result.may_submit}"
        )
        print("Text fields: correctly filled")
        print("Country select: untouched")
        print("Resume upload: untouched")
        print("Form submission: not triggered")


if __name__ == "__main__":
    main()