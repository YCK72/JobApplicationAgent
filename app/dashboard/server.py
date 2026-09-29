from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlsplit
import webbrowser

from app.dashboard.tracker_reader import (
    DEFAULT_WORKBOOK_PATH,
    DashboardDataError,
    TrackerWorkbookReader,
)


STATIC_DIR = Path(__file__).with_name("static")
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/static/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/static/app.js": (
        "app.js",
        "text/javascript; charset=utf-8",
    ),
}


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
    ) -> None:
        super().__init__(server_address, request_handler)
        self.reader = reader
        self.static_dir = static_dir


class DashboardRequestHandler(BaseHTTPRequestHandler):
    server: DashboardServer

    def do_GET(self) -> None:
        self._handle(include_body=True)

    def do_HEAD(self) -> None:
        self._handle(include_body=False)

    def do_POST(self) -> None:
        self._method_not_allowed()

    def do_PUT(self) -> None:
        self._method_not_allowed()

    def do_PATCH(self) -> None:
        self._method_not_allowed()

    def do_DELETE(self) -> None:
        self._method_not_allowed()

    def _handle(self, *, include_body: bool) -> None:
        path = urlsplit(self.path).path

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

        self._send_json(
            HTTPStatus.OK,
            snapshot,
            include_body=include_body,
        )

    def _method_not_allowed(self) -> None:
        body = json.dumps({
            "error": "Dashboard is read-only."
        }).encode("utf-8")
        self.send_response(HTTPStatus.METHOD_NOT_ALLOWED)
        self.send_header("Allow", "GET, HEAD")
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
) -> DashboardServer:
    if not isinstance(port, int) or not 0 <= port <= 65535:
        raise ValueError("port must be an integer from 0 to 65535")
    if not isinstance(host, str) or not host.strip():
        raise ValueError("host must not be empty")

    return DashboardServer(
        (host.strip(), port),
        DashboardRequestHandler,
        reader=reader,
        static_dir=static_dir,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Serve a read-only live dashboard for the exported Excel tracker."
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
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--open-browser",
        action="store_true",
        help="Open the dashboard in the default browser after startup.",
    )
    args = parser.parse_args(argv)

    try:
        server = create_dashboard_server(
            reader=TrackerWorkbookReader(args.workbook),
            host=args.host,
            port=args.port,
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
    print("Read-only live refresh is enabled. Press Ctrl+C to stop.")

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
