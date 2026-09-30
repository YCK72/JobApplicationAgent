from unittest.mock import MagicMock

from app.applications.submission_executor import (
    BrowserSubmissionExecutor,
    BrowserSubmissionStatus,
)


TARGET = "https://careers.tiktok.com/resume/123/apply"


def page_with(*, button_labels, body_text, current_url=TARGET, blocked=False):
    page = MagicMock()
    page.url = current_url
    controls = MagicMock()
    controls.count.return_value = len(button_labels)
    candidates = []
    for label in button_labels:
        candidate = MagicMock()
        candidate.is_visible.return_value = True
        candidate.is_enabled.return_value = True
        candidate.evaluate.return_value = "button"
        candidate.inner_text.return_value = label
        candidates.append(candidate)
    controls.nth.side_effect = candidates
    body = MagicMock()
    body.inner_text.return_value = body_text

    def locator(selector):
        if selector == "button, input[type='submit'], input[type='button']":
            return controls
        if selector == "body":
            return body
        gate = MagicMock()
        gate.count.return_value = 1 if blocked else 0
        return gate

    page.locator.side_effect = locator
    return page, candidates


def test_exact_submit_control_clicks_and_confirms_success():
    page, candidates = page_with(
        button_labels=["Submit application"],
        body_text="Thank you for applying. Your application was submitted.",
    )

    result = BrowserSubmissionExecutor(page).submit(target_url=TARGET)

    assert result.status == BrowserSubmissionStatus.CONFIRMED
    assert result.submitted is True
    assert result.success_confirmed is True
    assert result.evidence
    candidates[0].click.assert_called_once()


def test_ambiguous_submit_controls_fail_before_clicking():
    page, candidates = page_with(
        button_labels=["Submit", "Apply"],
        body_text="Application form",
    )

    result = BrowserSubmissionExecutor(page).submit(target_url=TARGET)

    assert result.status == BrowserSubmissionStatus.BLOCKED
    assert all(not candidate.click.called for candidate in candidates)


def test_security_or_account_gate_fails_before_clicking():
    page, candidates = page_with(
        button_labels=["Submit application"],
        body_text="Create account",
        blocked=True,
    )

    result = BrowserSubmissionExecutor(page).submit(target_url=TARGET)

    assert result.status == BrowserSubmissionStatus.BLOCKED
    candidates[0].click.assert_not_called()


def test_click_without_confirmation_is_unconfirmed():
    page, candidates = page_with(
        button_labels=["Submit application"],
        body_text="We are processing your request.",
    )

    result = BrowserSubmissionExecutor(page).submit(target_url=TARGET)

    assert result.status == BrowserSubmissionStatus.UNCONFIRMED
    assert result.submitted is True
    assert result.success_confirmed is False
    candidates[0].click.assert_called_once()
