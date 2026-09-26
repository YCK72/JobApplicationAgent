from pathlib import Path

import pytest

from app.applications.adapters.base import (
    ApplicationFormAdapter,
)
from app.applications.adapters.detector import (
    ATSProvider,
)
from app.applications.adapters.registry import (
    ApplicationAdapterRegistry,
)
from app.applications.answer_resolver import (
    ApplicationAnswerResolver,
)
from app.applications.form_analyzer import (
    ApplicationFormAnalyzer,
)
from app.applications.form_models import (
    ApplicationForm,
    FormField,
    FormFieldType,
)
from app.applications.form_plan import (
    ApplicationFormPlanner,
    FieldAction,
    FormPlanStatus,
)
from app.applications.form_validator import (
    ApplicationFormValidator,
)
from app.applications.inspection_service import (
    ApplicationInspectionService,
    InspectionOutcome,
)
from app.applications.question_policy import (
    ApplicationQuestionPolicy,
)
from app.jobs.models import (
    ApplicationStatus,
    Job,
)
from app.tracking.database import JobDatabase


class FakeGreenhouseAdapter(
    ApplicationFormAdapter
):
    def __init__(
        self,
        form: ApplicationForm,
    ) -> None:
        self.form = form
        self.inspect_calls = 0

    @property
    def provider_name(self) -> str:
        return "Greenhouse"

    def inspect(self) -> ApplicationForm:
        self.inspect_calls += 1
        return self.form


@pytest.fixture
def database(tmp_path: Path):
    return JobDatabase(
        tmp_path / "inspection_test.db"
    )


@pytest.fixture
def analyzer():
    resolver = ApplicationAnswerResolver(
        verified_answers={
            "first_name": "Test",
            "last_name": "Candidate",
            "email": "test@example.com",
        },
        question_policy=ApplicationQuestionPolicy(),
    )

    return ApplicationFormAnalyzer(
        answer_resolver=resolver
    )


@pytest.fixture
def planner():
    return ApplicationFormPlanner()


def make_job(
    *,
    url="https://boards.greenhouse.io/example/jobs/123",
    status=ApplicationStatus.READY_TO_APPLY,
    notes=None,
):
    return Job(
        company="Example Company",
        title="Software Engineer I",
        location="Seattle, WA",
        url=url,
        source="Test",
        status=status,
        notes=notes,
    )


def make_safe_form():
    return ApplicationForm(
        provider="Greenhouse",
        job_url=(
            "https://boards.greenhouse.io/"
            "example/jobs/123"
        ),
        fields=[
            FormField(
                field_id="first_name",
                label="First Name",
                field_type=FormFieldType.TEXT,
                required=True,
            ),
            FormField(
                field_id="email",
                label="Email",
                field_type=FormFieldType.EMAIL,
                required=True,
            ),
        ],
    )


def build_service(
    adapter,
    analyzer,
    planner,
    database,
):
    registry = ApplicationAdapterRegistry(
        {
            ATSProvider.GREENHOUSE: adapter,
        }
    )

    return ApplicationInspectionService(
        registry=registry,
        analyzer=analyzer,
        planner=planner,
        database=database,
        form_validator=ApplicationFormValidator(),
    )


def persist_job(
    database,
    job,
):
    return database.add_job(job)


def test_safe_form_remains_ready_to_apply(
    analyzer,
    planner,
    database,
):
    job = make_job()
    job_id = persist_job(database, job)

    adapter = FakeGreenhouseAdapter(
        make_safe_form()
    )

    service = build_service(
        adapter,
        analyzer,
        planner,
        database,
    )

    result = service.inspect(
        job,
        job_id,
    )

    assert (
        result.outcome
        == InspectionOutcome.INSPECTED
    )
    assert result.inspection_succeeded is True

    assert (
        result.provider
        == ATSProvider.GREENHOUSE
    )

    assert (
        job.status
        == ApplicationStatus.READY_TO_APPLY
    )

    stored = database.get_job_by_id(job_id)

    assert stored is not None
    assert (
        stored.status
        == ApplicationStatus.READY_TO_APPLY
    )

    assert result.form is not None
    assert result.plan is not None

    assert (
        result.plan.status
        == FormPlanStatus.AUTO_FILL_ALLOWED
    )

    assert result.plan.may_submit is False
    assert adapter.inspect_calls == 1


def test_verified_fields_receive_fill_actions(
    analyzer,
    planner,
    database,
):
    job = make_job()
    job_id = persist_job(database, job)

    adapter = FakeGreenhouseAdapter(
        make_safe_form()
    )

    service = build_service(
        adapter,
        analyzer,
        planner,
        database,
    )

    result = service.inspect(
        job,
        job_id,
    )

    assert result.plan is not None

    assert all(
        field.action
        == FieldAction.FILL_VERIFIED
        for field in result.plan.fields
    )

    assert [
        field.value
        for field in result.plan.fields
    ] == [
        "Test",
        "test@example.com",
    ]


@pytest.mark.parametrize(
    "status",
    [
        ApplicationStatus.DISCOVERED,
        ApplicationStatus.FILTERED_OUT,
        ApplicationStatus.NEEDS_APPLICATION,
        ApplicationStatus.NEEDS_REVIEW,
        ApplicationStatus.APPLIED,
        ApplicationStatus.REJECTED,
        ApplicationStatus.OFFER,
    ],
)
def test_non_ready_job_is_never_inspected(
    analyzer,
    planner,
    database,
    status,
):
    job = make_job(status=status)
    job_id = persist_job(database, job)

    adapter = FakeGreenhouseAdapter(
        make_safe_form()
    )

    service = build_service(
        adapter,
        analyzer,
        planner,
        database,
    )

    result = service.inspect(
        job,
        job_id,
    )

    assert (
        result.outcome
        == InspectionOutcome.NOT_ELIGIBLE
    )

    assert result.inspection_succeeded is False
    assert result.form is None
    assert result.plan is None

    assert adapter.inspect_calls == 0

    stored = database.get_job_by_id(job_id)

    assert stored is not None
    assert stored.status == status


def test_missing_job_id_fails_closed(
    analyzer,
    planner,
    database,
):
    job = make_job()

    adapter = FakeGreenhouseAdapter(
        make_safe_form()
    )

    service = build_service(
        adapter,
        analyzer,
        planner,
        database,
    )

    result = service.inspect(
        job,
        None,
    )

    assert (
        result.outcome
        == InspectionOutcome.NOT_ELIGIBLE
    )

    assert adapter.inspect_calls == 0

    assert (
        job.status
        == ApplicationStatus.READY_TO_APPLY
    )


def test_unknown_ats_moves_job_to_review(
    analyzer,
    planner,
    database,
):
    job = make_job(
        url="https://careers.example.com/jobs/123"
    )

    job_id = persist_job(database, job)

    adapter = FakeGreenhouseAdapter(
        make_safe_form()
    )

    service = build_service(
        adapter,
        analyzer,
        planner,
        database,
    )

    result = service.inspect(
        job,
        job_id,
    )

    assert (
        result.outcome
        == InspectionOutcome.NEEDS_REVIEW
    )

    assert result.provider == ATSProvider.UNKNOWN
    assert result.form is None
    assert result.plan is None

    assert job.status == ApplicationStatus.NEEDS_REVIEW
    assert job.notes is not None

    stored = database.get_job_by_id(job_id)

    assert stored is not None
    assert stored.status == ApplicationStatus.NEEDS_REVIEW
    assert stored.notes == job.notes

    assert adapter.inspect_calls == 0


def test_unregistered_ats_moves_job_to_review(
    analyzer,
    planner,
    database,
):
    job = make_job(
        url="https://jobs.lever.co/example/123"
    )

    job_id = persist_job(database, job)

    adapter = FakeGreenhouseAdapter(
        make_safe_form()
    )

    service = build_service(
        adapter,
        analyzer,
        planner,
        database,
    )

    result = service.inspect(
        job,
        job_id,
    )

    assert (
        result.outcome
        == InspectionOutcome.NEEDS_REVIEW
    )

    assert result.provider == ATSProvider.LEVER
    assert result.form is None
    assert result.plan is None

    assert job.status == ApplicationStatus.NEEDS_REVIEW

    stored = database.get_job_by_id(job_id)

    assert stored is not None
    assert stored.status == ApplicationStatus.NEEDS_REVIEW
    assert stored.notes == job.notes

    assert adapter.inspect_calls == 0


def test_review_plan_moves_job_to_review(
    analyzer,
    planner,
    database,
):
    job = make_job()
    job_id = persist_job(database, job)

    form = ApplicationForm(
        provider="Greenhouse",
        job_url=str(job.url),
        fields=[
            FormField(
                field_id="first_name",
                label="First Name",
            ),
            FormField(
                field_id="why_company",
                label=(
                    "Why do you want to work "
                    "at this company?"
                ),
                field_type=FormFieldType.TEXTAREA,
            ),
        ],
    )

    adapter = FakeGreenhouseAdapter(form)

    service = build_service(
        adapter,
        analyzer,
        planner,
        database,
    )

    result = service.inspect(
        job,
        job_id,
    )

    assert (
        result.outcome
        == InspectionOutcome.NEEDS_REVIEW
    )

    assert result.plan is not None

    assert (
        result.plan.status
        == FormPlanStatus.REVIEW_REQUIRED
    )

    assert (
        result.plan.fields[0].action
        == FieldAction.FILL_VERIFIED
    )

    assert (
        result.plan.fields[1].action
        == FieldAction.SKIP_REVIEW
    )

    assert job.status == ApplicationStatus.NEEDS_REVIEW

    stored = database.get_job_by_id(job_id)

    assert stored is not None
    assert stored.status == ApplicationStatus.NEEDS_REVIEW
    assert stored.notes == job.notes


def test_sensitive_plan_moves_job_to_review(
    analyzer,
    planner,
    database,
):
    job = make_job()
    job_id = persist_job(database, job)

    form = ApplicationForm(
        provider="Greenhouse",
        job_url=str(job.url),
        fields=[
            FormField(
                field_id="sponsorship",
                label=(
                    "Will you now or in the future "
                    "require sponsorship?"
                ),
            ),
        ],
    )

    adapter = FakeGreenhouseAdapter(form)

    service = build_service(
        adapter,
        analyzer,
        planner,
        database,
    )

    result = service.inspect(
        job,
        job_id,
    )

    assert (
        result.outcome
        == InspectionOutcome.NEEDS_REVIEW
    )

    assert result.plan is not None

    assert (
        result.plan.status
        == FormPlanStatus.MANUAL_REQUIRED
    )

    assert (
        result.plan.fields[0].action
        == FieldAction.SKIP_MANUAL
    )

    assert result.plan.fields[0].value is None

    assert job.status == ApplicationStatus.NEEDS_REVIEW

    stored = database.get_job_by_id(job_id)

    assert stored is not None
    assert stored.status == ApplicationStatus.NEEDS_REVIEW
    assert stored.notes == job.notes


def test_adapter_provider_mismatch_moves_job_to_review(
    analyzer,
    planner,
    database,
):
    job = make_job()
    job_id = persist_job(database, job)

    form = ApplicationForm(
        provider="Lever",
        job_url=str(job.url),
        fields=[],
    )

    adapter = FakeGreenhouseAdapter(form)

    service = build_service(
        adapter,
        analyzer,
        planner,
        database,
    )

    result = service.inspect(
        job,
        job_id,
    )

    assert (
        result.outcome
        == InspectionOutcome.NEEDS_REVIEW
    )

    assert result.form is form
    assert result.plan is None

    assert job.status == ApplicationStatus.NEEDS_REVIEW

    stored = database.get_job_by_id(job_id)

    assert stored is not None
    assert stored.status == ApplicationStatus.NEEDS_REVIEW
    assert stored.notes == job.notes


def test_adapter_wrong_job_url_moves_job_to_review(
    analyzer,
    planner,
    database,
):
    job = make_job()
    job_id = persist_job(database, job)

    form = ApplicationForm(
        provider="Greenhouse",
        job_url=(
            "https://boards.greenhouse.io/"
            "example/jobs/999"
        ),
        fields=[],
    )

    adapter = FakeGreenhouseAdapter(form)

    service = build_service(
        adapter,
        analyzer,
        planner,
        database,
    )

    result = service.inspect(
        job,
        job_id,
    )

    assert (
        result.outcome
        == InspectionOutcome.NEEDS_REVIEW
    )

    assert result.form is form
    assert result.plan is None

    assert job.status == ApplicationStatus.NEEDS_REVIEW

    stored = database.get_job_by_id(job_id)

    assert stored is not None
    assert stored.status == ApplicationStatus.NEEDS_REVIEW
    assert stored.notes == job.notes


def test_existing_notes_are_preserved(
    analyzer,
    planner,
    database,
):
    job = make_job(
        url="https://careers.example.com/jobs/123",
        notes="Existing note.",
    )

    job_id = persist_job(database, job)

    adapter = FakeGreenhouseAdapter(
        make_safe_form()
    )

    service = build_service(
        adapter,
        analyzer,
        planner,
        database,
    )

    service.inspect(
        job,
        job_id,
    )

    assert job.notes is not None
    assert job.notes.startswith("Existing note.")

    assert (
        "Application ATS could not be identified safely."
        in job.notes
    )

    stored = database.get_job_by_id(job_id)

    assert stored is not None
    assert stored.notes == job.notes


def test_database_failure_rolls_back_in_memory_state(
    analyzer,
    planner,
    database,
    monkeypatch,
):
    job = make_job(
        url="https://careers.example.com/jobs/123",
        notes="Original note.",
    )

    job_id = persist_job(database, job)

    adapter = FakeGreenhouseAdapter(
        make_safe_form()
    )

    service = build_service(
        adapter,
        analyzer,
        planner,
        database,
    )

    def fail_update(*args, **kwargs):
        raise RuntimeError(
            "Simulated database failure"
        )

    monkeypatch.setattr(
        database,
        "update_application_state",
        fail_update,
    )

    with pytest.raises(
        RuntimeError,
        match="Simulated database failure",
    ):
        service.inspect(
            job,
            job_id,
        )

    assert (
        job.status
        == ApplicationStatus.READY_TO_APPLY
    )

    assert job.notes == "Original note."

    stored = database.get_job_by_id(job_id)

    assert stored is not None

    assert (
        stored.status
        == ApplicationStatus.READY_TO_APPLY
    )

    assert stored.notes == "Original note."