import pytest

from app.jobs.eligibility import JobEligibilityGate, EligibilityStatus
from app.jobs.models import Job


def job(text, title="Software Engineer I"):
    return Job(company="Example", title=title, url="https://example.com/jobs/1",
               source="Test", location="Seattle, WA", description=text)


def gate(**facts):
    return JobEligibilityGate({"candidate": {
        "education": {"highest_degree": {"graduation": {"year": 2026, "month": 5}}},
        "eligibility": facts,
    }})


@pytest.mark.parametrize("text", [
    "Legally authorized to work without current or future sponsorship.",
    "We do not provide visa sponsorship.",
    "Visa sponsorship is not available for this role.",
    "Applicants must not require sponsorship now or in the future.",
    "We cannot sponsor visas.",
])
def test_explicit_no_sponsorship_mismatch(text):
    assert gate(requires_sponsorship=True).evaluate(job(text)).status == EligibilityStatus.INELIGIBLE


def test_unknown_sponsorship_requires_review():
    result = gate().evaluate(job("Visa sponsorship is not available."))
    assert result.status == EligibilityStatus.NEEDS_REVIEW
    assert result.findings


def test_sponsorship_requirement_matches_explicit_fact():
    assert gate(requires_sponsorship=False).evaluate(job("No visa sponsorship available.")).status == EligibilityStatus.CLEAR


@pytest.mark.parametrize("text", [
    "Visa sponsorship may be available.",
    "Sponsorship is considered case by case.",
    "We cannot sponsor visas except for certain roles.",
    "Visa sponsorship is not available. Visa sponsorship is available.",
])
def test_ambiguous_or_conflicting_sponsorship_is_review(text):
    assert gate(requires_sponsorship=True).evaluate(job(text)).status == EligibilityStatus.NEEDS_REVIEW


@pytest.mark.parametrize("text", [
    "Applicants must graduate between December 2026 and August 2027.",
    "Anticipated graduation date between December 2026 and August 2027.",
])
def test_explicit_graduation_window_mismatch(text):
    assert gate().evaluate(job(text)).status == EligibilityStatus.INELIGIBLE


@pytest.mark.parametrize("text", [
    "Graduation date between May 2026 and August 2027.",
    "Graduation date between January 2025 and May 2026.",
])
def test_graduation_window_boundaries_are_inclusive(text):
    assert gate().evaluate(job(text)).status == EligibilityStatus.CLEAR


@pytest.mark.parametrize("text", [
    "Graduation date between Fall 2025 and Summer 2026.",
    "Recent graduates only.",
    "Graduate by June 2026.",
])
def test_uncertain_graduation_wording_is_review(text):
    assert gate().evaluate(job(text)).status == EligibilityStatus.NEEDS_REVIEW


def test_missing_graduation_fact_is_review():
    assert JobEligibilityGate({}).evaluate(job("Graduation date between May 2026 and August 2026.")).status == EligibilityStatus.NEEDS_REVIEW


@pytest.mark.parametrize("enrolled,expected", [(True, EligibilityStatus.CLEAR), (False, EligibilityStatus.INELIGIBLE), (None, EligibilityStatus.NEEDS_REVIEW)])
def test_explicit_student_requirement(enrolled, expected):
    assert gate(currently_enrolled=enrolled).evaluate(job("Must be currently enrolled in a degree program.")).status == expected


def test_pursuing_degree_is_student_requirement():
    assert gate(currently_enrolled=False).evaluate(job("Currently pursuing a bachelor's or master's degree.")).status == EligibilityStatus.INELIGIBLE


def test_student_or_graduate_alternative_is_not_rejected():
    result = gate(currently_enrolled=False).evaluate(job("Must be pursuing or have recently completed a bachelor's degree."))
    assert result.status == EligibilityStatus.NEEDS_REVIEW


@pytest.mark.parametrize("clearance,expected", [("secret", EligibilityStatus.CLEAR), ("none", EligibilityStatus.INELIGIBLE), (None, EligibilityStatus.NEEDS_REVIEW), ("top_secret", EligibilityStatus.NEEDS_REVIEW)])
def test_active_clearance_requires_exact_verified_level(clearance, expected):
    assert gate(active_clearance=clearance).evaluate(job("An active Secret security clearance is required.")).status == expected


def test_higher_specific_clearance_is_not_inferred():
    assert gate(active_clearance="secret").evaluate(job("Must hold an active Top Secret security clearance.")).status == EligibilityStatus.NEEDS_REVIEW


@pytest.mark.parametrize("text", [
    "Must be able to obtain a security clearance.",
    "U.S. clearance eligibility may be required depending on program.",
    "Must be a U.S. Person due to access to export controlled information.",
    "U.S. citizenship is required.",
])
def test_legal_or_clearance_eligibility_requires_review(text):
    assert gate().evaluate(job(text)).status == EligibilityStatus.NEEDS_REVIEW


@pytest.mark.parametrize("text", [
    "Build Python services.",
    "Security clearance is not required.",
    "An active Secret security clearance is preferred.",
    "Current enrollment is preferred, not required.",
    "We sponsor community events.",
    "We do not discriminate based on citizenship, age, or national origin.",
])
def test_irrelevant_preferred_and_negated_requirements_do_not_block(text):
    assert gate().evaluate(job(text)).status == EligibilityStatus.CLEAR


def test_missing_description_is_review():
    assert gate().evaluate(job(None)).status == EligibilityStatus.NEEDS_REVIEW


def test_related_job_sidebar_does_not_add_requirements():
    text = "Build Python services.\n## Similar jobs\nMust hold an active Secret clearance."
    assert gate().evaluate(job(text)).status == EligibilityStatus.CLEAR


def test_confirmed_mismatch_takes_precedence_over_unknown_fact():
    text = "Graduation date between December 2026 and August 2027. No visa sponsorship available."
    assert gate().evaluate(job(text)).status == EligibilityStatus.INELIGIBLE


@pytest.mark.parametrize("facts", [{"requires_sponsorship": "false"}, {"currently_enrolled": 0}, {"active_clearance": True}, {"active_clearance": "yes"}])
def test_invalid_facts_fail_configuration(facts):
    with pytest.raises(ValueError):
        gate(**facts)


def test_invalid_graduation_fails_configuration():
    with pytest.raises(ValueError):
        JobEligibilityGate({"candidate": {"education": {"highest_degree": {"graduation": {"year": 2026, "month": 13}}}}})


@pytest.mark.parametrize("text", [
    "Visa sponsorship is not available, with exceptions for some roles.",
    "We cannot sponsor visas unless an exception is approved.",
])
def test_sponsorship_exceptions_never_create_confirmed_mismatch(text):
    assert gate(requires_sponsorship=True).evaluate(job(text)).status == EligibilityStatus.NEEDS_REVIEW


def test_no_sponsorship_restriction_does_not_block():
    result = gate(requires_sponsorship=True).evaluate(
        job("No sponsorship restrictions apply.")
    )
    assert result.status == EligibilityStatus.CLEAR


@pytest.mark.parametrize("text", [
    "Must be currently enrolled or a recent graduate.",
    "Must be currently enrolled or have graduated within the last year.",
    "Candidates should be currently enrolled, or equivalent experience is accepted.",
])
def test_student_alternatives_need_review(text):
    assert gate(currently_enrolled=False).evaluate(job(text)).status == EligibilityStatus.NEEDS_REVIEW


def test_clearance_alternative_does_not_reject_no_active_clearance():
    assert gate(active_clearance="none").evaluate(job(
        "Must hold an active Secret clearance or be willing to obtain one."
    )).status == EligibilityStatus.NEEDS_REVIEW


def test_explicit_requirement_after_preference_is_not_discarded():
    result = gate(requires_sponsorship=True).evaluate(job(
        "Python experience preferred; visa sponsorship is not available."
    ))
    assert result.status == EligibilityStatus.INELIGIBLE


def test_negated_student_requirement_does_not_reject():
    assert gate(currently_enrolled=False).evaluate(job(
        "Applicants do not need to be currently enrolled."
    )).status == EligibilityStatus.CLEAR


def test_graduation_alternative_is_not_an_explicit_mismatch():
    assert gate().evaluate(job(
        "Graduation date between December 2026 and August 2027 or equivalent experience."
    )).status == EligibilityStatus.NEEDS_REVIEW


def test_graduation_title_is_checked_when_description_has_no_dates():
    assert gate().evaluate(job("Build Python services.", title=
        "Software Engineer (Graduation Date: December 2026-August 2027)"
    )).status != EligibilityStatus.CLEAR


def test_boolean_fact_does_not_convert_visa_status_into_enrollment():
    configured = JobEligibilityGate({"candidate": {"eligibility": {
        "immigration_status": "F1", "requires_sponsorship": True,
        "ead_valid_from": "2026-06-29", "ead_valid_until": "2027-06-28",
    }}})
    assert configured.evaluate(job("Must be currently enrolled.")).status == EligibilityStatus.NEEDS_REVIEW
    assert configured.evaluate(job("No visa sponsorship available.")).status == EligibilityStatus.INELIGIBLE
