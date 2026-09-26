import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.jobs.models import (
    ApplicationMethod,
    ApplicationStatus,
    CompanyRule,
    Job,
    JobCategory,
    SeniorityLevel,
)


DEFAULT_DB_PATH = Path("database/jobs.db")


class JobDatabase:
    """
    SQLite persistence layer for the Job Application Agent.

    SQLite is the authoritative source of truth for discovered jobs
    and their application state.
    """

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)

        # Ensure the database directory exists.
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._initialize_database()

    # ---------------------------------------------------------
    # Connection
    # ---------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)

        # Allows rows to behave like dictionaries.
        connection.row_factory = sqlite3.Row

        # Enforce foreign-key relationships.
        connection.execute("PRAGMA foreign_keys = ON")

        return connection

    # ---------------------------------------------------------
    # Database initialization
    # ---------------------------------------------------------

    def _initialize_database(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,

                    company TEXT NOT NULL,
                    title TEXT NOT NULL,
                    location TEXT,
                    url TEXT NOT NULL UNIQUE,
                    source TEXT NOT NULL,

                    description TEXT,
                    external_job_id TEXT,
                    date_posted TEXT,

                    category TEXT NOT NULL,
                    seniority TEXT NOT NULL,

                    fit_score REAL,
                    fit_explanation TEXT,

                    priority_company INTEGER NOT NULL DEFAULT 0,
                    company_rule TEXT NOT NULL,
                    application_method TEXT NOT NULL,
                    status TEXT NOT NULL,

                    resume_used TEXT,

                    date_found TEXT NOT NULL,
                    date_applied TEXT,

                    notes TEXT,

                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_jobs_company
                ON jobs(company)
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_jobs_status
                ON jobs(status)
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_jobs_external_job_id
                ON jobs(external_job_id)
                """
            )

            connection.commit()

    # ---------------------------------------------------------
    # Insert
    # ---------------------------------------------------------

    def add_job(self, job: Job) -> int:
        """
        Insert a job into SQLite.

        Returns the SQLite row ID.

        Raises:
            ValueError:
                If a job with the same URL already exists.
        """

        if self.job_exists(job.url.encoded_string()):
            raise ValueError(
                f"Job already exists: {job.url.encoded_string()}"
            )

        now = datetime.now().isoformat()

        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO jobs (
                    company,
                    title,
                    location,
                    url,
                    source,
                    description,
                    external_job_id,
                    date_posted,
                    category,
                    seniority,
                    fit_score,
                    fit_explanation,
                    priority_company,
                    company_rule,
                    application_method,
                    status,
                    resume_used,
                    date_found,
                    date_applied,
                    notes,
                    created_at,
                    updated_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?
                )
                """,
                (
                    job.company,
                    job.title,
                    job.location,
                    job.url.encoded_string(),
                    job.source,
                    job.description,
                    job.external_job_id,
                    (
                        job.date_posted.isoformat()
                        if job.date_posted
                        else None
                    ),
                    job.category.value,
                    job.seniority.value,
                    job.fit_score,
                    job.fit_explanation,
                    int(job.priority_company),
                    job.company_rule.value,
                    job.application_method.value,
                    job.status.value,
                    job.resume_used,
                    job.date_found.isoformat(),
                    (
                        job.date_applied.isoformat()
                        if job.date_applied
                        else None
                    ),
                    job.notes,
                    now,
                    now,
                ),
            )

            connection.commit()

            return int(cursor.lastrowid)

    # ---------------------------------------------------------
    # Duplicate detection
    # ---------------------------------------------------------

    def job_exists(self, url: str) -> bool:
        """
        Return True if the URL already exists in the database.
        """

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM jobs
                WHERE url = ?
                LIMIT 1
                """,
                (url,),
            ).fetchone()

        return row is not None

    # ---------------------------------------------------------
    # Retrieval
    # ---------------------------------------------------------

    def get_job_by_id(self, job_id: int) -> Optional[Job]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM jobs
                WHERE id = ?
                """,
                (job_id,),
            ).fetchone()

        if row is None:
            return None

        return self._row_to_job(row)

    def get_job_by_url(self, url: str) -> Optional[Job]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM jobs
                WHERE url = ?
                """,
                (url,),
            ).fetchone()

        if row is None:
            return None

        return self._row_to_job(row)

    def get_all_jobs(self) -> list[Job]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM jobs
                ORDER BY date_found DESC
                """
            ).fetchall()

        return [self._row_to_job(row) for row in rows]

    # ---------------------------------------------------------
    # Updates
    # ---------------------------------------------------------

    def update_status(
        self,
        job_id: int,
        status: ApplicationStatus,
    ) -> None:
        now = datetime.now().isoformat()

        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs
                SET status = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    status.value,
                    now,
                    job_id,
                ),
            )

            if cursor.rowcount == 0:
                raise ValueError(
                    f"Job ID {job_id} does not exist."
                )

            connection.commit()

    def update_application_state(
        self,
        job_id: int,
        status: ApplicationStatus,
        notes: Optional[str] = None,
    ) -> None:
        """
        Atomically persist application lifecycle state and notes.

        This is used when a lifecycle transition has an explanatory
        reason that must remain consistent with the persisted status.
        """

        now = datetime.now().isoformat()

        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs
                SET status = ?,
                    notes = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    status.value,
                    notes,
                    now,
                    job_id,
                ),
            )

            if cursor.rowcount == 0:
                raise ValueError(
                    f"Job ID {job_id} does not exist."
                )

            connection.commit()

    def update_fit_score(
        self,
        job_id: int,
        fit_score: float,
        explanation: Optional[str] = None,
    ) -> None:
        if not 0 <= fit_score <= 100:
            raise ValueError(
                "fit_score must be between 0 and 100."
            )

        now = datetime.now().isoformat()

        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs
                SET fit_score = ?,
                    fit_explanation = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    fit_score,
                    explanation,
                    now,
                    job_id,
                ),
            )

            if cursor.rowcount == 0:
                raise ValueError(
                    f"Job ID {job_id} does not exist."
                )

            connection.commit()

    def mark_applied(
        self,
        job_id: int,
        resume_used: Optional[str] = None,
    ) -> None:
        """
        Mark an application as successfully submitted.

        IMPORTANT:
        This method records state only. It does not perform browser
        submission and must only be called after submission has been
        independently confirmed.
        """

        now = datetime.now()

        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs
                SET status = ?,
                    date_applied = ?,
                    resume_used = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    ApplicationStatus.APPLIED.value,
                    now.isoformat(),
                    resume_used,
                    now.isoformat(),
                    job_id,
                ),
            )

            if cursor.rowcount == 0:
                raise ValueError(
                    f"Job ID {job_id} does not exist."
                )

            connection.commit()

    # ---------------------------------------------------------
    # Conversion
    # ---------------------------------------------------------

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> Job:
        return Job(
            company=row["company"],
            title=row["title"],
            location=row["location"],
            url=row["url"],
            source=row["source"],
            description=row["description"],
            external_job_id=row["external_job_id"],
            date_posted=row["date_posted"],
            category=JobCategory(row["category"]),
            seniority=SeniorityLevel(row["seniority"]),
            fit_score=row["fit_score"],
            fit_explanation=row["fit_explanation"],
            priority_company=bool(row["priority_company"]),
            company_rule=CompanyRule(row["company_rule"]),
            application_method=ApplicationMethod(
                row["application_method"]
            ),
            status=ApplicationStatus(row["status"]),
            resume_used=row["resume_used"],
            date_found=row["date_found"],
            date_applied=row["date_applied"],
            notes=row["notes"],
        )