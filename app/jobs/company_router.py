from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.jobs.models import ApplicationMethod, CompanyRule, Job


@dataclass(frozen=True)
class CompanyRoutingResult:
    """
    Result of resolving a raw company name against company_rules.yaml.
    """

    original_company: str
    normalized_company: str
    canonical_company: str
    rule: CompanyRule
    priority_company: bool
    matched: bool


class CompanyRouter:
    """
    Resolves company names and determines whether a job should be handled
    manually, automatically, or blocked.

    Routing decisions come from config/company_rules.yaml rather than being
    hard-coded into application logic.
    """

    def __init__(self, config: dict[str, Any]):
        if not isinstance(config, dict):
            raise ValueError("Company rules configuration must be a dictionary.")

        self.config = config

        default_rule_value = config.get("default_rule", "AUTO")

        try:
            self.default_rule = CompanyRule(str(default_rule_value).upper())
        except ValueError as exc:
            raise ValueError(
                f"Invalid default company rule: {default_rule_value}"
            ) from exc

        companies = config.get("companies", {})

        if companies is None:
            companies = {}

        if not isinstance(companies, dict):
            raise ValueError(
                "'companies' in company_rules.yaml must be a dictionary."
            )

        self.companies = companies
        self._alias_index = self._build_alias_index()

    @staticmethod
    def normalize_company_name(company_name: str) -> str:
        """
        Normalize a company name for deterministic comparison.

        Examples:
            "Microsoft Corporation" -> "microsoft corporation"
            "  GOOGLE LLC "         -> "google llc"
            "Amazon.com"            -> "amazon com"
        """

        if not company_name:
            return ""

        normalized = company_name.strip().lower()

        # Convert punctuation and separators into spaces.
        normalized = re.sub(r"[^a-z0-9]+", " ", normalized)

        # Collapse repeated whitespace.
        normalized = re.sub(r"\s+", " ", normalized)

        return normalized.strip()

    def _build_alias_index(self) -> dict[str, str]:
        """
        Build:

            normalized alias -> canonical company name

        This allows company matching to remain fast and deterministic.
        """

        alias_index: dict[str, str] = {}

        for canonical_company, company_config in self.companies.items():
            if not isinstance(company_config, dict):
                raise ValueError(
                    f"Configuration for '{canonical_company}' "
                    "must be a dictionary."
                )

            names_to_index = [canonical_company]

            aliases = company_config.get("aliases", [])

            if aliases is None:
                aliases = []

            if not isinstance(aliases, list):
                raise ValueError(
                    f"Aliases for '{canonical_company}' must be a list."
                )

            names_to_index.extend(aliases)

            for name in names_to_index:
                normalized = self.normalize_company_name(str(name))

                if not normalized:
                    continue

                existing = alias_index.get(normalized)

                if existing and existing != canonical_company:
                    raise ValueError(
                        f"Company alias collision: '{name}' is assigned to "
                        f"both '{existing}' and '{canonical_company}'."
                    )

                alias_index[normalized] = canonical_company

        return alias_index

    def resolve(self, company_name: str) -> CompanyRoutingResult:
        """
        Resolve a raw company name into its canonical company and routing rule.
        """

        if not company_name or not company_name.strip():
            raise ValueError("Company name cannot be empty.")

        normalized = self.normalize_company_name(company_name)

        canonical_company = self._alias_index.get(normalized)

        if canonical_company is None:
            return CompanyRoutingResult(
                original_company=company_name,
                normalized_company=normalized,
                canonical_company=company_name.strip(),
                rule=self.default_rule,
                priority_company=False,
                matched=False,
            )

        company_config = self.companies[canonical_company]

        rule_value = company_config.get("rule", self.default_rule.value)

        try:
            rule = CompanyRule(str(rule_value).upper())
        except ValueError as exc:
            raise ValueError(
                f"Invalid company rule '{rule_value}' "
                f"for '{canonical_company}'."
            ) from exc

        priority = bool(company_config.get("priority", rule == CompanyRule.MANUAL))

        return CompanyRoutingResult(
            original_company=company_name,
            normalized_company=normalized,
            canonical_company=canonical_company,
            rule=rule,
            priority_company=priority,
            matched=True,
        )

    def route_job(self, job: Job) -> Job:
        """
        Apply company-routing information to a Job object.

        MANUAL:
            application_method = MANUAL

        AUTO:
            application_method = AUTO

        BLOCKED:
            company rule is recorded, but the job must not proceed to an
            application workflow.

        This method does not submit applications or control the browser.
        """

        result = self.resolve(job.company)

        job.company = result.canonical_company
        job.priority_company = result.priority_company
        job.company_rule = result.rule

        if result.rule == CompanyRule.MANUAL:
            job.application_method = ApplicationMethod.MANUAL

        elif result.rule == CompanyRule.AUTO:
            job.application_method = ApplicationMethod.AUTO

        elif result.rule == CompanyRule.BLOCKED:
            # BLOCKED is intentionally not treated as AUTO.
            #
            # Later pipeline filtering will prevent blocked jobs from entering
            # application processing.
            job.application_method = ApplicationMethod.UNKNOWN

        return job