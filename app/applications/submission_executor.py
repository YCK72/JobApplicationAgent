from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from urllib.parse import urlsplit

from playwright.sync_api import Page


class BrowserSubmissionStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    UNCONFIRMED = "UNCONFIRMED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class BrowserSubmissionResult:
    status: BrowserSubmissionStatus
    reason: str
    submitted: bool = False
    success_confirmed: bool = False
    evidence: str | None = None


class BrowserSubmissionExecutor:
    """Submit one fully prepared form and verify explicit success evidence."""

    _SUBMIT_LABEL = re.compile(
        r"(?:submit(?: application)?|apply(?: now)?|finish application)",
        flags=re.IGNORECASE,
    )
    _SUCCESS = re.compile(
        r"thank you for applying|application (?:was |has been )?submitted|"
        r"successfully submitted|we (?:have )?received your application",
        flags=re.IGNORECASE,
    )
    _SECURITY_SELECTORS = (
        "input[type='password']",
        "iframe[src*='captcha' i]",
        "[id*='captcha' i]",
        "[class*='captcha' i]",
        "iframe[src*='challenge' i]",
    )
    _ACCOUNT_GATE = re.compile(
        r"sign in to (?:continue|apply)|create (?:an? )?account to apply|"
        r"verify (?:your )?email to continue",
        flags=re.IGNORECASE,
    )

    def __init__(self, page: Page) -> None:
        self._page = page

    def submit(self, *, target_url: str) -> BrowserSubmissionResult:
        if not self._same_host(target_url, self._page.url):
            return self._blocked(
                "The browser left the authorized application host before submission."
            )
        if self._has_security_gate():
            return self._blocked(
                "Account login, password creation, CAPTCHA, or verification is required."
            )

        candidates = self._submit_candidates()
        if len(candidates) != 1:
            return self._blocked(
                "The application did not expose exactly one unambiguous submit control."
            )

        try:
            candidates[0].click(timeout=10_000)
            try:
                self._page.wait_for_load_state("domcontentloaded", timeout=15_000)
            except Exception:
                pass
            try:
                self._page.wait_for_timeout(1_000)
            except Exception:
                pass
            text = self._page.locator("body").inner_text(timeout=10_000)
        except Exception as exc:
            return BrowserSubmissionResult(
                status=BrowserSubmissionStatus.FAILED,
                reason=f"Application submission click failed: {exc}",
            )

        match = self._SUCCESS.search(text or "")
        if match is not None:
            evidence = (
                f"Browser displayed '{match.group(0)}' at {self._page.url}."
            )
            return BrowserSubmissionResult(
                status=BrowserSubmissionStatus.CONFIRMED,
                reason="Application submission was confirmed by the destination page.",
                submitted=True,
                success_confirmed=True,
                evidence=evidence,
            )
        return BrowserSubmissionResult(
            status=BrowserSubmissionStatus.UNCONFIRMED,
            reason=(
                "The submit control was activated, but the destination did not "
                "provide recognized confirmation evidence."
            ),
            submitted=True,
            success_confirmed=False,
            evidence=f"Post-submit browser URL: {self._page.url}",
        )

    def _submit_candidates(self) -> list[object]:
        controls = self._page.locator(
            "button, input[type='submit'], input[type='button']"
        )
        matches = []
        for index in range(controls.count()):
            control = controls.nth(index)
            try:
                if not control.is_visible() or not control.is_enabled():
                    continue
                tag_name = control.evaluate(
                    "(element) => element.tagName.toLowerCase()"
                )
                label = (
                    control.get_attribute("value")
                    if tag_name == "input"
                    else control.inner_text()
                )
            except Exception:
                continue
            normalized = " ".join((label or "").split())
            if self._SUBMIT_LABEL.fullmatch(normalized):
                matches.append(control)
        return matches

    def _has_security_gate(self) -> bool:
        for selector in self._SECURITY_SELECTORS:
            controls = self._page.locator(selector)
            for index in range(controls.count()):
                try:
                    if controls.nth(index).is_visible():
                        return True
                except Exception:
                    return True
        try:
            body_text = self._page.locator("body").inner_text(timeout=5_000)
        except Exception:
            return True
        if self._ACCOUNT_GATE.search(body_text or "") is not None:
            return True
        return False

    @staticmethod
    def _same_host(expected: str, current: str) -> bool:
        try:
            expected_url = urlsplit(expected)
            current_url = urlsplit(current)
        except ValueError:
            return False
        return (
            expected_url.scheme.lower() == "https"
            and current_url.scheme.lower() == "https"
            and expected_url.hostname is not None
            and expected_url.hostname == current_url.hostname
        )

    @staticmethod
    def _blocked(reason: str) -> BrowserSubmissionResult:
        return BrowserSubmissionResult(
            status=BrowserSubmissionStatus.BLOCKED,
            reason=reason,
        )
