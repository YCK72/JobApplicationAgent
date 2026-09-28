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

RESUME_DIRECTORY = (
    PROJECT_ROOT
    / "data"
    / "resumes"
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


def find_smoke_test_resume() -> Path:
    """
    Select one existing local PDF deterministically for the controlled
    browser smoke test.

    This helper is test infrastructure only. Production resume selection
    remains the responsibility of the resume-routing layer.
    """
    if not RESUME_DIRECTORY.is_dir():
        raise RuntimeError(
            f"Resume directory does not exist: {RESUME_DIRECTORY}"
        )

    resume_candidates = sorted(
        (
            path.resolve()
            for path in RESUME_DIRECTORY.glob("*.pdf")
            if path.is_file()
        ),
        key=lambda path: path.name.casefold(),
    )

    if not resume_candidates:
        raise RuntimeError(
            "No PDF resume is available for the controlled smoke test."
        )

    return resume_candidates[0]


def main() -> None:
    if not FIXTURE_PATH.is_file():
        raise RuntimeError(
            f"Fixture does not exist: {FIXTURE_PATH}"
        )

    resume_path = find_smoke_test_resume()

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
        make_field(
            "resume",
            "Resume",
            FormFieldType.FILE,
        ),
    )

    values = (
        "Test",
        "test@example.com",
        "555-0100",
        "Controlled local smoke test.",
        "United States",
        str(resume_path),
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

        if result.completed_actions != 6:
            raise RuntimeError(
                "Expected exactly six completed actions."
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

        resume = page.locator("#resume")

        attached_file = resume.evaluate(
            """element => {
                if (!element.files || element.files.length !== 1) {
                    return null;
                }

                return {
                    name: element.files[0].name,
                    size: element.files[0].size
                };
            }"""
        )

        if not isinstance(attached_file, dict):
            raise RuntimeError(
                "Resume input does not contain exactly one attached file."
            )

        if attached_file.get("name") != resume_path.name:
            raise RuntimeError(
                "Attached resume filename does not match the expected file."
            )

        if attached_file.get("size") != resume_path.stat().st_size:
            raise RuntimeError(
                "Attached resume size does not match the expected file."
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
        print(
            "Resume upload: exactly one expected local PDF attached"
        )
        print("Form submission: not triggered")


if __name__ == "__main__":
    main()