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
    *,
    options: list[str] | None = None,
) -> FormField:
    return FormField(
        field_id=field_id,
        label=label,
        field_type=field_type,
        options=options or [],
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
        make_field(
            "country",
            "Country",
            FormFieldType.SELECT,
            options=[
                "Select a country",
                "United States",
                "Canada",
            ],
        ),
    )

    values = (
        "Test",
        "test@example.com",
        "555-0100",
        "Controlled local smoke test.",
        "United States",
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

        if result.completed_actions != 5:
            raise RuntimeError(
                "Expected exactly five completed actions."
            )

        if result.may_submit:
            raise RuntimeError(
                "Execution unexpectedly allowed submission."
            )

        actual_text_values = (
            page.locator("#first_name").input_value(),
            page.locator("#email").input_value(),
            page.locator("#phone").input_value(),
            page.locator("#short_answer").input_value(),
        )

        expected_text_values = values[:4]

        if actual_text_values != expected_text_values:
            raise RuntimeError(
                "Written text values do not match expected values."
            )

        country = page.locator("#country")

        country_value = country.input_value()

        if country_value != "US":
            raise RuntimeError(
                "Country SELECT did not resolve to the expected "
                "native option value."
            )

        selected_country_label = country.locator(
            "option:checked"
        ).text_content()

        if (
            selected_country_label is None
            or selected_country_label.strip() != "United States"
        ):
            raise RuntimeError(
                "Country SELECT did not preserve the expected "
                "visible option label."
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
        print(
            "Country select: United States "
            "(native value US)"
        )
        print("Resume upload: untouched")
        print("Form submission: not triggered")


if __name__ == "__main__":
    main()