from __future__ import annotations

import argparse
from copy import deepcopy
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import urlsplit
import webbrowser

from app.dashboard.tracker_reader import (
    DEFAULT_WORKBOOK_PATH,
    DashboardDataError,
    TrackerWorkbookReader,
)
from app.applications.target_review import (
    ApplicationTargetReviewService,
    TargetReviewStatus,
)
from app.dashboard.review_resolution import (
    ApplicationReviewResolutionService,
    ReviewResolutionStatus,
)
from app.dashboard.application_preview import (
    ApplicationPreviewService,
    ApplicationPreviewStatus,
)
from app.dashboard.application_launch import (
    ApplicationLaunchStatus,
    DashboardApplicationLaunchService,
    EXTERNAL_BROWSER_CONFIRMATION,
)
from app.dashboard.review_sessions import (
    ApplicationReviewSessionManager,
    ReviewSessionSnapshot,
)
from app.applications.composition import (
    build_single_job_application_launcher_from_dependencies,
)
from app.jobs.composition import build_job_pipeline
from app.tracking.database import DEFAULT_DB_PATH, JobDatabase
from app.tracking.excel_tracker import ExcelTracker


STATIC_DIR = Path(__file__).with_name("static")
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/static/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/static/app.js": (
        "app.js",
        "text/javascript; charset=utf-8",
    ),
}
CLOSE_REVIEW_SESSION_CONFIRMATION = "CLOSE_REVIEW_SESSION"


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        request_handler,
        *,
        reader: TrackerWorkbookReader,
        static_dir: Path,
        target_review_service: ApplicationTargetReviewService | None,
        review_resolution_service: ApplicationReviewResolutionService | None,
        application_preview_service: ApplicationPreviewService | None,
        application_launch_service: DashboardApplicationLaunchService | None,
    ) -> None:
        super().__init__(server_address, request_handler)
        self.reader = reader
        self.static_dir = static_dir
        self.target_review_service = target_review_service
        self.review_resolution_service = review_resolution_service
        self.application_preview_service = application_preview_service
        self.application_launch_service = application_launch_service

    def server_close(self) -> None:
        if self.application_launch_service is not None:
            self.application_launch_service.close_all_review_sessions()
        super().server_close()


class DashboardRequestHandler(BaseHTTPRequestHandler):
    server: DashboardServer

    def do_GET(self) -> None:
        self._handle(include_body=True)

    def do_HEAD(self) -> None:
        self._handle(include_body=False)

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        match = re.fullmatch(
            r"/api/jobs/([1-9][0-9]*)/application-target",
            path,
        )
        if match and self.server.target_review_service is not None:
            self._assign_application_target(int(match.group(1)))
            return
        match = re.fullmatch(
            r"/api/jobs/([1-9][0-9]*)/review-resolution",
            path,
        )
        if match and self.server.review_resolution_service is not None:
            self._record_review_resolution(int(match.group(1)))
            return
        match = re.fullmatch(
            r"/api/jobs/([1-9][0-9]*)/application-launch",
            path,
        )
        if match and self.server.application_launch_service is not None:
            self._launch_application(int(match.group(1)))
            return
        match = re.fullmatch(
            r"/api/jobs/([1-9][0-9]*)/review-session/close",
            path,
        )
        if match and self.server.application_launch_service is not None:
            self._close_review_session(int(match.group(1)))
            return
        self._method_not_allowed()

    def do_PUT(self) -> None:
        self._method_not_allowed()

    def do_PATCH(self) -> None:
        self._method_not_allowed()

    def do_DELETE(self) -> None:
        self._method_not_allowed()

    def _handle(self, *, include_body: bool) -> None:
        path = urlsplit(self.path).path

        history_match = re.fullmatch(
            r"/api/jobs/([1-9][0-9]*)/review-history",
            path,
        )
        if (
            history_match
            and self.server.review_resolution_service is not None
        ):
            self._serve_review_history(
                int(history_match.group(1)),
                include_body=include_body,
            )
            return

        preview_match = re.fullmatch(
            r"/api/jobs/([1-9][0-9]*)/application-preview",
            path,
        )
        if preview_match and (
            self.server.application_preview_service is not None
            or self.server.application_launch_service is not None
        ):
            self._serve_application_preview(
                int(preview_match.group(1)),
                include_body=include_body,
            )
            return

        if path == "/api/jobs":
            self._serve_jobs(include_body=include_body)
            return

        if path == "/api/health":
            self._send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "workbook_available": (
                        self.server.reader.workbook_path.is_file()
                    ),
                },
                include_body=include_body,
            )
            return

        static_file = STATIC_FILES.get(path)
        if static_file is None:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"error": "Not found."},
                include_body=include_body,
            )
            return

        filename, content_type = static_file
        try:
            content = (
                self.server.static_dir / filename
            ).read_bytes()
        except OSError:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "Dashboard asset is unavailable."},
                include_body=include_body,
            )
            return

        self._send(
            HTTPStatus.OK,
            content,
            content_type,
            include_body=include_body,
        )

    def _serve_jobs(self, *, include_body: bool) -> None:
        try:
            snapshot = self.server.reader.snapshot()
        except DashboardDataError as exc:
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": str(exc)},
                include_body=include_body,
            )
            return

        reviewer = self.server.target_review_service
        resolver = self.server.review_resolution_service
        previewer = self.server.application_preview_service
        database = (
            reviewer.database
            if reviewer is not None
            else resolver.database
            if resolver is not None
            else previewer.database if previewer is not None else None
        )
        if database is not None:
            snapshot = deepcopy(snapshot)
            for item in snapshot["jobs"]:
                source_url = item.get("job_url")
                stored_record = (
                    database.get_job_with_id_by_url(source_url)
                    if source_url
                    else None
                )
                item["job_id"] = None
                item["target_review_eligible"] = False
                if stored_record is not None:
                    job_id, stored = stored_record
                    item["job_id"] = job_id
                    item["target_review_eligible"] = (
                        reviewer.is_eligible(stored)
                        if reviewer is not None
                        else False
                    )
                    if resolver is not None:
                        item.update(resolver.apply_latest(job_id, item))
                    if self.server.application_launch_service is not None:
                        review_session = (
                            self.server.application_launch_service
                            .current_review_session(job_id)
                        )
                        item["review_session_active"] = (
                            review_session is not None
                        )
                        item["review_session_expires_in_seconds"] = (
                            review_session.expires_in_seconds
                            if review_session is not None
                            else None
                        )
            snapshot["metrics"]["review_queue"] = sum(
                item.get("review_required") is True
                for item in snapshot["jobs"]
            )

        self._send_json(
            HTTPStatus.OK,
            snapshot,
            include_body=include_body,
        )

    def _serve_application_preview(
        self,
        job_id: int,
        *,
        include_body: bool,
    ) -> None:
        try:
            launch_service = self.server.application_launch_service
            prepared = (
                launch_service.prepare(job_id)
                if launch_service is not None
                else None
            )
            result = (
                prepared.preview
                if prepared is not None
                else self.server.application_preview_service.preview(job_id)
            )
        except Exception:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "Application preview could not be loaded."},
                include_body=include_body,
            )
            return

        status_code = {
            ApplicationPreviewStatus.READY: HTTPStatus.OK,
            ApplicationPreviewStatus.BLOCKED: HTTPStatus.OK,
            ApplicationPreviewStatus.NOT_FOUND: HTTPStatus.NOT_FOUND,
            ApplicationPreviewStatus.FAILED: HTTPStatus.INTERNAL_SERVER_ERROR,
        }[result.status]
        job = result.job
        authorization = None
        if prepared is not None and prepared.authorization_token is not None:
            authorization = {
                "token": prepared.authorization_token,
                "expires_in_seconds": (
                    prepared.authorization_expires_in_seconds
                ),
                "confirmation": EXTERNAL_BROWSER_CONFIRMATION,
            }
        self._send_json(
            status_code,
            {
                "status": result.status.value,
                "reason": result.reason,
                "job_id": result.job_id,
                "job": (
                    {
                        "company": job.company,
                        "title": job.title,
                        "location": job.location,
                        "fit_score": job.fit_score,
                        "application_status": job.status.value,
                    }
                    if job is not None
                    else None
                ),
                "source_url": result.source_url,
                "application_url": result.application_url,
                "ats_provider": result.provider.value,
                "resume": result.resume,
                "safety": {
                    "browser_started": result.browser_started,
                    "workflow_ran": result.workflow_ran,
                    "external_authorization_required": True,
                    "fields_filled": False,
                    "files_uploaded": False,
                    "may_submit": result.may_submit,
                },
                "authorization": authorization,
                "review_session": self._review_session_payload(
                    prepared.review_session
                    if prepared is not None
                    else None
                ),
            },
            include_body=include_body,
        )

    def _launch_application(self, job_id: int) -> None:
        if self.headers.get_content_type() != "application/json":
            self._send_json(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                {"error": "Content-Type must be application/json."},
                include_body=True,
            )
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if not 1 <= length <= 8192:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "Request body must contain 1-8192 bytes."},
                include_body=True,
            )
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "Request body must be valid JSON."},
                include_body=True,
            )
            return
        if not isinstance(payload, dict):
            payload = {}
        token = payload.get("authorization_token")
        confirmation = payload.get("confirmation")
        if (
            not isinstance(token, str)
            or not token
            or confirmation != EXTERNAL_BROWSER_CONFIRMATION
        ):
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": (
                        "A fresh preview token and exact external-browser "
                        "confirmation are required."
                    )
                },
                include_body=True,
            )
            return

        try:
            result = self.server.application_launch_service.launch(
                job_id=job_id,
                authorization_token=token,
                confirmation=confirmation,
            )
        except Exception:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "Application launch failed unexpectedly."},
                include_body=True,
            )
            return

        status_code = {
            ApplicationLaunchStatus.READY_FOR_REVIEW: HTTPStatus.OK,
            ApplicationLaunchStatus.AUTHORIZATION_DENIED: HTTPStatus.FORBIDDEN,
            ApplicationLaunchStatus.AUTHORIZATION_EXPIRED: HTTPStatus.FORBIDDEN,
            ApplicationLaunchStatus.PREVIEW_STALE: HTTPStatus.CONFLICT,
            ApplicationLaunchStatus.SESSION_ACTIVE: HTTPStatus.CONFLICT,
            ApplicationLaunchStatus.SESSION_UNAVAILABLE: (
                HTTPStatus.INTERNAL_SERVER_ERROR
            ),
            ApplicationLaunchStatus.NOT_FOUND: HTTPStatus.NOT_FOUND,
            ApplicationLaunchStatus.NOT_ELIGIBLE: HTTPStatus.CONFLICT,
            ApplicationLaunchStatus.NEEDS_REVIEW: HTTPStatus.CONFLICT,
            ApplicationLaunchStatus.BLOCKED: HTTPStatus.CONFLICT,
            ApplicationLaunchStatus.FAILED: HTTPStatus.INTERNAL_SERVER_ERROR,
        }[result.status]
        self._send_json(
            status_code,
            {
                "status": result.status.value,
                "reason": result.reason,
                "job_id": result.job_id,
                "completed_actions": result.completed_actions,
                "application_status": (
                    result.application_status.value
                    if result.application_status is not None
                    else None
                ),
                "export_path": (
                    str(result.export_path)
                    if result.export_path is not None
                    else None
                ),
                "may_submit": result.may_submit,
                "review_session": self._review_session_payload(
                    result.review_session
                ),
            },
            include_body=True,
        )

    def _close_review_session(self, job_id: int) -> None:
        if self.headers.get_content_type() != "application/json":
            self._send_json(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                {"error": "Content-Type must be application/json."},
                include_body=True,
            )
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if not 1 <= length <= 8192:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "Request body must contain 1-8192 bytes."},
                include_body=True,
            )
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "Request body must be valid JSON."},
                include_body=True,
            )
            return
        confirmation = (
            payload.get("confirmation")
            if isinstance(payload, dict)
            else None
        )
        if confirmation != CLOSE_REVIEW_SESSION_CONFIRMATION:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "Exact review-session close confirmation is required."},
                include_body=True,
            )
            return

        try:
            closed = self.server.application_launch_service.close_review_session(
                job_id
            )
        except Exception:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "Review session could not be closed."},
                include_body=True,
            )
            return
        self._send_json(
            HTTPStatus.OK if closed else HTTPStatus.NOT_FOUND,
            {
                "status": "CLOSED" if closed else "NOT_FOUND",
                "job_id": job_id,
                "active": False,
            },
            include_body=True,
        )

    @staticmethod
    def _review_session_payload(
        session: ReviewSessionSnapshot | None,
    ) -> dict[str, Any] | None:
        if session is None:
            return None
        return {
            "job_id": session.job_id,
            "target_url": session.target_url,
            "active": session.active,
            "expires_in_seconds": session.expires_in_seconds,
        }

    def _assign_application_target(self, job_id: int) -> None:
        content_type = self.headers.get_content_type()
        if content_type != "application/json":
            self._send_json(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                {"error": "Content-Type must be application/json."},
                include_body=True,
            )
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if not 1 <= length <= 8192:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "Request body must contain 1-8192 bytes."},
                include_body=True,
            )
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "Request body must be valid JSON."},
                include_body=True,
            )
            return
        application_url = (
            payload.get("application_url")
            if isinstance(payload, dict)
            else None
        )
        if not isinstance(application_url, str) or not application_url.strip():
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "application_url must be a non-empty string."},
                include_body=True,
            )
            return

        try:
            result = self.server.target_review_service.assign(
                job_id=job_id,
                application_url=application_url,
            )
        except Exception:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "Application target could not be updated."},
                include_body=True,
            )
            return

        status_code = {
            TargetReviewStatus.UPDATED: HTTPStatus.OK,
            TargetReviewStatus.NOT_FOUND: HTTPStatus.NOT_FOUND,
            TargetReviewStatus.NOT_ELIGIBLE: HTTPStatus.CONFLICT,
            TargetReviewStatus.INVALID_TARGET: HTTPStatus.UNPROCESSABLE_ENTITY,
            TargetReviewStatus.REPROCESS_BLOCKED: HTTPStatus.CONFLICT,
        }[result.status]
        self._send_json(
            status_code,
            {
                "status": result.status.value,
                "reason": result.reason,
                "job_id": result.job_id,
                "application_url": result.application_url,
                "pipeline_outcome": (
                    result.pipeline_outcome.value
                    if result.pipeline_outcome
                    else None
                ),
            },
            include_body=True,
        )

    def _serve_review_history(
        self,
        job_id: int,
        *,
        include_body: bool,
    ) -> None:
        try:
            history = self.server.review_resolution_service.history(job_id)
        except Exception:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "Review history could not be loaded."},
                include_body=include_body,
            )
            return

        self._send_json(
            HTTPStatus.OK,
            {
                "job_id": job_id,
                "history": [
                    {
                        "resolution_id": record.resolution_id,
                        "review_kind": record.review_kind,
                        "outcome": record.outcome.value,
                        "note": record.note,
                        "recorded_at": record.created_at,
                    }
                    for record in history
                ],
            },
            include_body=include_body,
        )

    def _record_review_resolution(self, job_id: int) -> None:
        if self.headers.get_content_type() != "application/json":
            self._send_json(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                {"error": "Content-Type must be application/json."},
                include_body=True,
            )
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if not 1 <= length <= 8192:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "Request body must contain 1-8192 bytes."},
                include_body=True,
            )
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "Request body must be valid JSON."},
                include_body=True,
            )
            return
        if not isinstance(payload, dict):
            payload = {}

        try:
            result = self.server.review_resolution_service.record(
                job_id=job_id,
                outcome=payload.get("outcome"),
                note=payload.get("note"),
            )
        except Exception:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "Review decision could not be recorded."},
                include_body=True,
            )
            return

        status_code = {
            ReviewResolutionStatus.RECORDED: HTTPStatus.OK,
            ReviewResolutionStatus.INVALID: HTTPStatus.BAD_REQUEST,
            ReviewResolutionStatus.NOT_FOUND: HTTPStatus.NOT_FOUND,
            ReviewResolutionStatus.NOT_REQUIRED: HTTPStatus.CONFLICT,
        }[result.status]
        record = result.record
        self._send_json(
            status_code,
            {
                "status": result.status.value,
                "reason": result.reason,
                "job_id": result.job_id,
                "outcome": record.outcome.value if record else None,
                "review_kind": record.review_kind if record else None,
                "note": record.note if record else None,
                "recorded_at": record.created_at if record else None,
                "tracker_error": result.tracker_error,
            },
            include_body=True,
        )

    def _method_not_allowed(self) -> None:
        body = json.dumps({
            "error": "Method not allowed."
        }).encode("utf-8")
        self.send_response(HTTPStatus.METHOD_NOT_ALLOWED)
        allowed = (
            "GET, HEAD, POST"
            if (
                self.server.target_review_service is not None
                or self.server.review_resolution_service is not None
                or self.server.application_launch_service is not None
            )
            else "GET, HEAD"
        )
        self.send_header("Allow", allowed)
        self._headers("application/json; charset=utf-8", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(
        self,
        status: HTTPStatus,
        payload: dict[str, Any],
        *,
        include_body: bool,
    ) -> None:
        body = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        self._send(
            status,
            body,
            "application/json; charset=utf-8",
            include_body=include_body,
        )

    def _send(
        self,
        status: HTTPStatus,
        body: bytes,
        content_type: str,
        *,
        include_body: bool,
    ) -> None:
        self.send_response(status)
        self._headers(content_type, len(body))
        self.end_headers()
        if include_body:
            self.wfile.write(body)

    def _headers(self, content_type: str, length: int) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; connect-src 'self'; "
            "img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; base-uri 'none'; form-action 'none'",
        )

    def log_message(self, format: str, *args: object) -> None:
        return


def create_dashboard_server(
    *,
    reader: TrackerWorkbookReader,
    host: str = "127.0.0.1",
    port: int = 8765,
    static_dir: Path = STATIC_DIR,
    target_review_service: ApplicationTargetReviewService | None = None,
    review_resolution_service: ApplicationReviewResolutionService | None = None,
    application_preview_service: ApplicationPreviewService | None = None,
    application_launch_service: DashboardApplicationLaunchService | None = None,
) -> DashboardServer:
    if not isinstance(port, int) or not 0 <= port <= 65535:
        raise ValueError("port must be an integer from 0 to 65535")
    if not isinstance(host, str) or not host.strip():
        raise ValueError("host must not be empty")
    if (
        (
            target_review_service is not None
            or review_resolution_service is not None
            or application_launch_service is not None
        )
        and host.strip().lower() not in {"127.0.0.1", "::1", "localhost"}
    ):
        raise ValueError("Editable dashboard requires a loopback host.")

    return DashboardServer(
        (host.strip(), port),
        DashboardRequestHandler,
        reader=reader,
        static_dir=static_dir,
        target_review_service=target_review_service,
        review_resolution_service=review_resolution_service,
        application_preview_service=application_preview_service,
        application_launch_service=application_launch_service,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Serve the local Excel tracker and guarded target-review dashboard."
        )
    )
    parser.add_argument(
        "--workbook",
        type=Path,
        default=DEFAULT_WORKBOOK_PATH,
        help=(
            "Tracker workbook path "
            "(default: data/exports/Job_Application_Tracker.xlsx)"
        ),
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="SQLite database path (default: database/jobs.db)",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--review-session-minutes",
        type=float,
        default=15,
        help="Minutes to keep a filled browser open for review (default: 15).",
    )
    parser.add_argument(
        "--open-browser",
        action="store_true",
        help="Open the dashboard in the default browser after startup.",
    )
    args = parser.parse_args(argv)

    try:
        database = JobDatabase(args.database)
        tracker = ExcelTracker(database, args.workbook)
        reviewer = ApplicationTargetReviewService(
            database=database,
            pipeline=build_job_pipeline(database=database),
            tracker=tracker,
        )
        resolution_service = ApplicationReviewResolutionService(
            database=database,
            tracker=tracker,
        )
        preview_service = ApplicationPreviewService(database=database)
        review_session_manager = ApplicationReviewSessionManager(
            review_ttl_seconds=args.review_session_minutes * 60,
        )
        launcher = build_single_job_application_launcher_from_dependencies(
            database=database,
            tracker=tracker,
            execution_session_factory=(
                review_session_manager.create_execution_session
            ),
        )
        launch_service = DashboardApplicationLaunchService(
            preview_service=preview_service,
            launcher=launcher,
            review_session_manager=review_session_manager,
        )
        server = create_dashboard_server(
            reader=TrackerWorkbookReader(args.workbook),
            host=args.host,
            port=args.port,
            target_review_service=reviewer,
            review_resolution_service=resolution_service,
            application_preview_service=preview_service,
            application_launch_service=launch_service,
        )
    except (OSError, ValueError) as exc:
        print(f"Dashboard could not start: {exc}", file=sys.stderr)
        return 2

    display_host = (
        "127.0.0.1"
        if args.host in {"0.0.0.0", "::"}
        else args.host
    )
    url = f"http://{display_host}:{server.server_port}"
    print(f"Dashboard: {url}")
    print(f"Workbook: {args.workbook.resolve()}")
    print("Live refresh and reviewed target assignment are enabled.")
    print("Press Ctrl+C to stop.")

    if args.open_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
