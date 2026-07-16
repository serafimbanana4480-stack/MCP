"""Self-contained web dashboard for ProjectMind.

Serves a professional dark-themed HTML dashboard backed by the ProjectMind
usage/telemetry data. Uses only the Python standard library (`http.server`),
no pip dependencies. The HTML/JS is pure and works even without network access
(Chart.js is loaded from a CDN but has a table fallback).
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


def run_dashboard(root: str, host: str = "127.0.0.1", port: int = 8777) -> None:
    """Build a ProjectMind instance and serve the web dashboard.

    Args:
        root: Project root path to inspect.
        host: Bind host (default 127.0.0.1).
        port: Bind port (default 8777).
    """
    # Lazy import to avoid pulling heavy deps at module import time.
    from ..application import ProjectMind

    app = ProjectMind(root)
    template_path = Path(__file__).parent / "templates" / "dashboard.html"

    try:
        dashboard_html = template_path.read_text(encoding="utf-8")
    except OSError:
        dashboard_html = "<h1>ProjectMind Dashboard</h1><p>template not found</p>"

    class Handler(BaseHTTPRequestHandler):
        server_version = "ProjectMindDashboard/0.1"

        def _send(self, code, body: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?", 1)[0]

            if path in ("/", "/index.html"):
                self._send(200, dashboard_html.encode("utf-8"), "text/html; charset=utf-8")
                return

            if path == "/api/usage":
                payload = json.dumps(app.tool_usage_dashboard_data(), default=str)
                self._send(200, payload.encode("utf-8"), "application/json")
                return

            if path == "/api/health":
                payload = json.dumps({"status": "ok", "root": str(root)}, default=str)
                self._send(200, payload.encode("utf-8"), "application/json")
                return

            self._send(404, b'{"error":"not found"}', "application/json")

        def log_message(self, fmt: str, *args) -> None:  # quieter logging
            print(f"[dashboard] {fmt % args}")

    class ReusableServer(HTTPServer):
        allow_reuse_address = True

    url = f"http://{host}:{port}"
    server = ReusableServer((host, port), Handler)
    print(f"ProjectMind Dashboard running at {url}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down dashboard.")
    finally:
        server.server_close()
