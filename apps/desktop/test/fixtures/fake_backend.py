"""Stands in for `python -m suzent.server` in the desktop tests."""

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = os.environ.get("FAKE_SOURCE_ROOT") or None
VERSION = os.environ.get("FAKE_VERSION", "0.0.0")
TOKEN = os.environ["SUZENT_SERVICE_CONTROL_TOKEN"]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args: object) -> None:
        pass

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send(
                200,
                {"app": "suzent", "status": "ok", "version": VERSION, "source_root": ROOT},
            )
        else:
            self._send(404, {})

    def do_POST(self) -> None:
        if self.path == "/service/stop" and self.headers.get("X-Suzent-Service-Token") == TOKEN:
            self._send(200, {"ok": True})
            threading.Thread(target=server.shutdown).start()
        else:
            self._send(403, {})


server = HTTPServer(("127.0.0.1", 0), Handler)
runtime = Path(os.environ["SUZENT_DATA_DIR"]) / "runtime"
(runtime / "server.port").write_text(str(server.server_address[1]))
if os.environ.get("FAKE_EXIT_EARLY"):
    sys.exit(3)
server.serve_forever()
