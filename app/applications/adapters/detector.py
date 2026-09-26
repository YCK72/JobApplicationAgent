from __future__ import annotations

from enum import Enum
from urllib.parse import urlparse


class ATSProvider(str, Enum):
    GREENHOUSE = "GREENHOUSE"
    LEVER = "LEVER"
    ASHBY = "ASHBY"
    WORKDAY = "WORKDAY"
    UNKNOWN = "UNKNOWN"


class ATSDetector:
    """
    Deterministically identifies a supported ATS provider from
    known URL hostnames.

    Detection is intentionally conservative. Unknown or ambiguous
    URLs fail closed to ATSProvider.UNKNOWN.
    """

    GREENHOUSE_HOSTS = {
        "boards.greenhouse.io",
        "job-boards.greenhouse.io",
    }

    LEVER_HOSTS = {
        "jobs.lever.co",
    }

    ASHBY_HOSTS = {
        "jobs.ashbyhq.com",
    }

    @classmethod
    def detect(
        cls,
        url: str,
    ) -> ATSProvider:
        """
        Detect an ATS provider from a job/application URL.

        Only explicitly recognized hostnames are accepted.
        """

        if not isinstance(url, str):
            return ATSProvider.UNKNOWN

        normalized = url.strip()

        if not normalized:
            return ATSProvider.UNKNOWN

        try:
            parsed = urlparse(normalized)
        except ValueError:
            return ATSProvider.UNKNOWN

        hostname = parsed.hostname

        if not hostname:
            return ATSProvider.UNKNOWN

        hostname = hostname.lower().rstrip(".")

        if hostname in cls.GREENHOUSE_HOSTS:
            return ATSProvider.GREENHOUSE

        if hostname in cls.LEVER_HOSTS:
            return ATSProvider.LEVER

        if hostname in cls.ASHBY_HOSTS:
            return ATSProvider.ASHBY

        if cls._is_workday_host(hostname):
            return ATSProvider.WORKDAY

        return ATSProvider.UNKNOWN

    @staticmethod
    def _is_workday_host(
        hostname: str,
    ) -> bool:
        """
        Recognize tenant-specific Workday recruiting hosts.

        Examples:
            company.wd1.myworkdayjobs.com
            company.wd5.myworkdayjobs.com
        """

        return (
            hostname.endswith(".myworkdayjobs.com")
            or hostname == "myworkdayjobs.com"
        )