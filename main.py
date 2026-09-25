from pathlib import Path

from app.tracking.database import JobDatabase
from app.tracking.excel_tracker import ExcelTracker
from app.utils.config import (
    ConfigError,
    load_candidate_config,
    load_company_rules,
    load_role_config,
)
from app.utils.logging import setup_logging


PROJECT_ROOT = Path(__file__).resolve().parent


def ensure_directories() -> None:
    """
    Ensure required runtime directories exist.
    """

    directories = [
        PROJECT_ROOT / "database",
        PROJECT_ROOT / "logs",
        PROJECT_ROOT / "data" / "exports",
        PROJECT_ROOT / "data" / "generated",
        PROJECT_ROOT / "data" / "browser_profile",
        PROJECT_ROOT / "data" / "resumes",
    ]

    for directory in directories:
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )


def main() -> None:
    logger = setup_logging()

    logger.info(
        "Starting Job Application Agent."
    )

    try:
        # -----------------------------------------------------
        # Runtime directories
        # -----------------------------------------------------

        ensure_directories()

        logger.info(
            "Runtime directories verified."
        )

        # -----------------------------------------------------
        # Configuration
        # -----------------------------------------------------

        candidate_config = (
            load_candidate_config()
        )

        company_rules = (
            load_company_rules()
        )

        role_config = (
            load_role_config()
        )

        logger.info(
            "Configuration files loaded successfully."
        )

        # -----------------------------------------------------
        # Database
        # -----------------------------------------------------

        database = JobDatabase()

        jobs = database.get_all_jobs()

        logger.info(
            "SQLite database initialized. "
            "Tracked jobs: %d",
            len(jobs),
        )

        # -----------------------------------------------------
        # Excel tracker
        # -----------------------------------------------------

        tracker = ExcelTracker(database)

        tracker_path = tracker.generate()

        logger.info(
            "Excel tracker generated: %s",
            tracker_path,
        )

        # Prevent linters from treating loaded configuration
        # as accidentally unused. These will be passed into
        # services beginning in Milestone 2.
        _ = (
            candidate_config,
            company_rules,
            role_config,
        )

        # -----------------------------------------------------
        # Ready
        # -----------------------------------------------------

        print()
        print("=" * 60)
        print("JOB APPLICATION AGENT")
        print("=" * 60)
        print("Status: READY")
        print(f"Tracked jobs: {len(jobs)}")
        print(f"Database: {database.db_path}")
        print(f"Excel tracker: {tracker_path}")
        print("=" * 60)

        logger.info(
            "Job Application Agent initialized successfully."
        )

    except ConfigError as exc:
        logger.error(
            "Configuration error: %s",
            exc,
        )

        raise SystemExit(1) from exc

    except Exception:
        logger.exception(
            "Unexpected startup error."
        )

        raise


if __name__ == "__main__":
    main()