from __future__ import annotations

from app.applications.resume_router import ResumeRouter
from app.jobs.classifier import RoleClassifier
from app.jobs.company_router import CompanyRouter
from app.jobs.eligibility import JobEligibilityGate
from app.jobs.filters import JobFilter
from app.jobs.pipeline import JobPipeline
from app.scoring.fit_gate import FitGate
from app.scoring.fit_scorer import FitScorer
from app.tracking.database import JobDatabase
from app.utils.config import (
    load_candidate_config,
    load_company_rules,
    load_role_config,
)


def build_job_pipeline(*, database: JobDatabase) -> JobPipeline:
    """Compose the deterministic production job pipeline.

    This boundary loads local configuration and connects classification,
    eligibility, scoring, resume routing, and persistence. It does not create
    a browser or invoke the application workflow.
    """

    candidate_config = load_candidate_config()
    company_rules = load_company_rules()
    role_config = load_role_config()

    return JobPipeline(
        company_router=CompanyRouter(company_rules),
        classifier=RoleClassifier(role_config),
        job_filter=JobFilter(role_config),
        fit_scorer=FitScorer(candidate_config),
        fit_gate=FitGate(role_config),
        resume_router=ResumeRouter(candidate_config),
        database=database,
        eligibility_gate=JobEligibilityGate(candidate_config),
    )
