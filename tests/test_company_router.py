import pytest

from app.jobs.company_router import CompanyRouter
from app.jobs.models import ApplicationMethod, CompanyRule


@pytest.fixture
def company_config():
    return {
        "default_rule": "AUTO",
        "companies": {
            "Microsoft": {
                "rule": "MANUAL",
                "priority": True,
                "aliases": [
                    "microsoft",
                    "microsoft corporation",
                    "microsoft corp",
                ],
            },
            "Amazon": {
                "rule": "MANUAL",
                "priority": True,
                "aliases": [
                    "amazon",
                    "amazon.com",
                    "amazon web services",
                    "aws",
                ],
            },
            "Google": {
                "rule": "MANUAL",
                "priority": True,
                "aliases": [
                    "google",
                    "google llc",
                    "google deepmind",
                ],
            },
            "Tesla": {
                "rule": "MANUAL",
                "priority": True,
                "aliases": [
                    "tesla",
                    "tesla inc",
                ],
            },
        },
    }


@pytest.fixture
def router(company_config):
    return CompanyRouter(company_config)


def test_microsoft_corporation_routes_manual(router):
    result = router.resolve("Microsoft Corporation")

    assert result.canonical_company == "Microsoft"
    assert result.rule == CompanyRule.MANUAL
    assert result.priority_company is True
    assert result.matched is True


def test_amazon_web_services_routes_manual(router):
    result = router.resolve("Amazon Web Services")

    assert result.canonical_company == "Amazon"
    assert result.rule == CompanyRule.MANUAL
    assert result.priority_company is True


def test_aws_routes_to_amazon(router):
    result = router.resolve("AWS")

    assert result.canonical_company == "Amazon"
    assert result.rule == CompanyRule.MANUAL


def test_google_llc_routes_manual(router):
    result = router.resolve("Google LLC")

    assert result.canonical_company == "Google"
    assert result.rule == CompanyRule.MANUAL


def test_tesla_routes_manual(router):
    result = router.resolve("Tesla")

    assert result.canonical_company == "Tesla"
    assert result.rule == CompanyRule.MANUAL


def test_matching_is_case_insensitive(router):
    result = router.resolve("MICROSOFT CORPORATION")

    assert result.canonical_company == "Microsoft"
    assert result.rule == CompanyRule.MANUAL


def test_matching_ignores_surrounding_whitespace(router):
    result = router.resolve("   Google LLC   ")

    assert result.canonical_company == "Google"


def test_unknown_company_uses_default_auto_rule(router):
    result = router.resolve("Example Startup")

    assert result.canonical_company == "Example Startup"
    assert result.rule == CompanyRule.AUTO
    assert result.priority_company is False
    assert result.matched is False


def test_empty_company_rejected(router):
    with pytest.raises(ValueError):
        router.resolve("")


def test_invalid_default_rule_rejected():
    config = {
        "default_rule": "INVALID",
        "companies": {},
    }

    with pytest.raises(ValueError):
        CompanyRouter(config)


def test_alias_collision_rejected():
    config = {
        "default_rule": "AUTO",
        "companies": {
            "Company A": {
                "rule": "MANUAL",
                "aliases": ["shared alias"],
            },
            "Company B": {
                "rule": "MANUAL",
                "aliases": ["shared alias"],
            },
        },
    }

    with pytest.raises(ValueError):
        CompanyRouter(config)