from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


class JobCategory(str, Enum):
    """Supported career-track classifications."""

    SDE = "SDE"
    DATA_SCIENCE = "DATA_SCIENCE"
    AI_ML = "AI_ML"
    IT = "IT"
    OTHER = "OTHER"


class SeniorityLevel(str, Enum):
    """Normalized seniority classification."""

    ENTRY_LEVEL = "ENTRY_LEVEL"
    EARLY_CAREER = "EARLY_CAREER"
    MID_LEVEL = "MID_LEVEL"
    SENIOR = "SENIOR"
    UNKNOWN = "UNKNOWN"


class CompanyRule(str, Enum):
    """Determines whether a company may receive automated applications."""

    MANUAL = "MANUAL"
    AUTO = "AUTO"
    BLOCKED = "BLOCKED"


class ApplicationMethod(str, Enum):
    """How an application should be handled."""

    MANUAL = "MANUAL"
    AUTO = "AUTO"
    REVIEW = "REVIEW"
    UNKNOWN = "UNKNOWN"


class ApplicationStatus(str, Enum):
    """Lifecycle state of a discovered job/application."""

    DISCOVERED = "DISCOVERED"
    FILTERED_OUT = "FILTERED_OUT"
    QUALIFIED = "QUALIFIED"
    NEEDS_APPLICATION = "NEEDS_APPLICATION"
    READY_TO_APPLY = "READY_TO_APPLY"
    FORM_STARTED = "FORM_STARTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    APPLIED = "APPLIED"
    SUBMISSION_UNCONFIRMED = "SUBMISSION_UNCONFIRMED"
    OA = "OA"
    INTERVIEW = "INTERVIEW"
    REJECTED = "REJECTED"
    OFFER = "OFFER"
    WITHDRAWN = "WITHDRAWN"
    ERROR = "ERROR"


class Job(BaseModel):
    """
    Normalized representation of a job posting.

    Every discovery source must convert its source-specific data
    into this model before the rest of the application processes it.
    """

    # ---------------------------------------------------------
    # Source information
    # ---------------------------------------------------------

    company: str = Field(min_length=1)
    title: str = Field(min_length=1)

    location: Optional[str] = None
    url: HttpUrl

    source: str = Field(min_length=1)

    description: Optional[str] = None

    external_job_id: Optional[str] = None
    date_posted: Optional[date] = None

    # ---------------------------------------------------------
    # Classification
    # ---------------------------------------------------------

    category: JobCategory = JobCategory.OTHER
    seniority: SeniorityLevel = SeniorityLevel.UNKNOWN

    # ---------------------------------------------------------
    # Fit analysis
    # ---------------------------------------------------------

    fit_score: Optional[float] = Field(
        default=None,
        ge=0,
        le=100,
    )

    fit_explanation: Optional[str] = None

    # ---------------------------------------------------------
    # Routing
    # ---------------------------------------------------------

    priority_company: bool = False

    company_rule: CompanyRule = CompanyRule.AUTO

    application_method: ApplicationMethod = (
        ApplicationMethod.UNKNOWN
    )

    # ---------------------------------------------------------
    # Application state
    # ---------------------------------------------------------

    status: ApplicationStatus = (
        ApplicationStatus.DISCOVERED
    )

    resume_used: Optional[str] = None

    # ---------------------------------------------------------
    # Tracking
    # ---------------------------------------------------------

    date_found: datetime = Field(
        default_factory=datetime.now
    )

    date_applied: Optional[datetime] = None

    notes: Optional[str] = None