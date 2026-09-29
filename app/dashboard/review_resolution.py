from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from app.dashboard.review_queue import build_review_queue_item
from app.tracking.database import JobDatabase
from app.tracking.excel_tracker import ExcelTracker


class ReviewResolutionOutcome(str, Enum):
    RESOLVED = "RESOLVED"
    DEFERRED = "DEFERRED"
    DISMISSED = "DISMISSED"


class ReviewResolutionStatus(str, Enum):
    RECORDED = "RECORDED"
    INVALID = "INVALID"
    NOT_FOUND = "NOT_FOUND"
    NOT_REQUIRED = "NOT_REQUIRED"


@dataclass(frozen=True)
class ReviewResolutionRecord:
    resolution_id: int
    job_id: int
    review_kind: str
    outcome: ReviewResolutionOutcome
    note: str
    created_at: str


@dataclass(frozen=True)
class ReviewResolutionResult:
    status: ReviewResolutionStatus
    reason: str
    job_id: int
    record: ReviewResolutionRecord | None = None
    export_path: Path | None = None
    tracker_error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.status == ReviewResolutionStatus.RECORDED


class ApplicationReviewResolutionService:
    """Persist dashboard review decisions without changing application state."""

    def __init__(
        self,
        *,
        database: JobDatabase,
        tracker: ExcelTracker,
    ) -> None:
        self.database = database
        self.tracker = tracker

    def record(
        self,
        *,
        job_id: int,
        outcome: object,
        note: object,
    ) -> ReviewResolutionResult:
        if isinstance(job_id, bool) or not isinstance(job_id, int) or job_id <= 0:
            raise ValueError("job_id must be a positive integer")

        try:
            parsed_outcome = ReviewResolutionOutcome(outcome)
        except (TypeError, ValueError):
            return ReviewResolutionResult(
                status=ReviewResolutionStatus.INVALID,
                reason="Review outcome must be RESOLVED, DEFERRED, or DISMISSED.",
                job_id=job_id,
            )

        cleaned_note = note.strip() if isinstance(note, str) else ""
        if len(cleaned_note) < 3 or len(cleaned_note) > 1000:
            return ReviewResolutionResult(
                status=ReviewResolutionStatus.INVALID,
                reason="Review note must contain 3 to 1000 characters.",
                job_id=job_id,
            )

        job = self.database.get_job_by_id(job_id)
        if job is None:
            return ReviewResolutionResult(
                status=ReviewResolutionStatus.NOT_FOUND,
                reason=f"Job ID {job_id} does not exist.",
                job_id=job_id,
            )

        review = build_review_queue_item(job.model_dump(mode="json"))
        review_kind = review.get("review_kind")
        if review.get("review_required") is not True or not isinstance(
            review_kind,
            str,
        ):
            return ReviewResolutionResult(
                status=ReviewResolutionStatus.NOT_REQUIRED,
                reason="The job does not currently require dashboard review.",
                job_id=job_id,
            )

        created_at = datetime.now().isoformat()
        resolution_id = self.database.add_review_resolution(
            job_id=job_id,
            review_kind=review_kind,
            outcome=parsed_outcome.value,
            note=cleaned_note,
            created_at=created_at,
        )
        record = ReviewResolutionRecord(
            resolution_id=resolution_id,
            job_id=job_id,
            review_kind=review_kind,
            outcome=parsed_outcome,
            note=cleaned_note,
            created_at=created_at,
        )

        try:
            export_path = self.tracker.generate()
        except Exception as exc:
            export_path = None
            tracker_error = str(exc)
        else:
            tracker_error = None

        return ReviewResolutionResult(
            status=ReviewResolutionStatus.RECORDED,
            reason="Review decision recorded without changing application state.",
            job_id=job_id,
            record=record,
            export_path=export_path,
            tracker_error=tracker_error,
        )

    def latest(
        self,
        job_id: int,
        review_kind: str,
    ) -> ReviewResolutionRecord | None:
        row = self.database.get_latest_review_resolution(job_id, review_kind)
        if row is None:
            return None
        return ReviewResolutionRecord(
            resolution_id=int(row["id"]),
            job_id=int(row["job_id"]),
            review_kind=str(row["review_kind"]),
            outcome=ReviewResolutionOutcome(str(row["outcome"])),
            note=str(row["note"]),
            created_at=str(row["created_at"]),
        )

    def history(self, job_id: int) -> list[ReviewResolutionRecord]:
        if isinstance(job_id, bool) or not isinstance(job_id, int) or job_id <= 0:
            raise ValueError("job_id must be a positive integer")
        return [
            ReviewResolutionRecord(
                resolution_id=int(row["id"]),
                job_id=int(row["job_id"]),
                review_kind=str(row["review_kind"]),
                outcome=ReviewResolutionOutcome(str(row["outcome"])),
                note=str(row["note"]),
                created_at=str(row["created_at"]),
            )
            for row in self.database.get_review_resolutions(job_id)
        ]

    def apply_latest(
        self,
        job_id: int,
        review: dict[str, Any],
    ) -> dict[str, Any]:
        enriched = dict(review)
        enriched.update({
            "review_outcome": None,
            "review_note": None,
            "review_recorded_at": None,
        })
        review_kind = enriched.get("review_kind")
        if not isinstance(review_kind, str):
            return enriched

        record = self.latest(job_id, review_kind)
        if record is None:
            return enriched

        enriched.update({
            "review_outcome": record.outcome.value,
            "review_note": record.note,
            "review_recorded_at": record.created_at,
        })
        if record.outcome in {
            ReviewResolutionOutcome.RESOLVED,
            ReviewResolutionOutcome.DISMISSED,
        }:
            enriched["review_required"] = False
        return enriched
