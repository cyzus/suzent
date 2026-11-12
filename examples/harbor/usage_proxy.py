"""Logging proxy between Suzent and an OpenAI-compatible model provider.

Benchmarks that price each model call need per-call token counts, and Suzent
reports one total per run. This proxy forwards every request unchanged and
appends one JSON line per chat completion to a log::

    {"t": 1794430000000, "status": 200, "prompt": 9120, "completion": 88, "cached": 8704}

``prompt`` includes ``cached`` (OpenAI semantics). A call that returned no
usage block is logged with ``"prompt": null``.

    python usage_proxy.py <port> <log.jsonl> <upstream origin>

Standard library only, so it runs with any Python in a task container.
"""

import http.client
import json
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

HEALTH_PATH = "/__usage_proxy_health"
_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-length",
}
_USAGE = re.compile(rb'"usage"\s*:\s*(\{(?:[^{}]|\{[^{}]*\})*\})')


def extract_usage(body: bytes) -> dict | None:
    """The last usage block in a response: the final SSE chunk, or a JSON body."""
    found = None
    for match in _USAGE.finditer(body):
        try:
            found = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
    return found


def usage_record(status: int, usage: dict | None) -> dict:
    usage = usage or {}
    details = usage.get("prompt_tokens_details") or {}
    return {
        "t": int(time.time() * 1000),
        "status": status,
        "prompt": usage.get("prompt_tokens"),
        "completion": usage.get("completion_tokens"),
        "cached": details.get("cached_tokens") or 0,
    }


def make_handler(upstream: str, log_path: Path) -> type[BaseHTTPRequestHandler]:
    origin = urlsplit(upstream)
    connect = (
        http.client.HTTPSConnection
        if origin.scheme == "https"
        else http.client.HTTPConnection
    )

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def _record(self, record: dict) -> None:
            with log_path.open("a", encoding="utf-8") as log:
                log.write(json.dumps(record) + "\n")

        def _forward(self) -> None:
            if self.path == HEALTH_PATH:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")
                return

            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            headers = {
                name: value
                for name, value in self.headers.items()
                # Uncompressed, so the usage block can be read as it passes.
                if name.lower() not in _HOP_BY_HOP | {"host", "accept-encoding"}
            }
            is_completion = "chat/completions" in self.path
            try:
                connection = connect(origin.netloc, timeout=600)
                connection.request(self.command, self.path, body or None, headers)
                response = connection.getresponse()
            except OSError as exc:
                if is_completion:
                    self._record({**usage_record(502, None), "error": str(exc)})
                self.send_error(502, str(exc))
                return

            self.send_response(response.status)
            for name, value in response.getheaders():
                if name.lower() not in _HOP_BY_HOP:
                    self.send_header(name, value)
            # No length is sent: the stream ends when this connection closes.
            self.send_header("Connection", "close")
            self.end_headers()
            received = bytearray()
            while chunk := response.read1(65536):
                received += chunk
                self.wfile.write(chunk)
                self.wfile.flush()
            connection.close()
            self.close_connection = True
            if is_completion:
                self._record(usage_record(response.status, extract_usage(received)))

        do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = _forward

    return Handler


def serve(port: int, log_path: Path, upstream: str) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(upstream, log_path))
    server.serve_forever()


if __name__ == "__main__":
    serve(int(sys.argv[1]), Path(sys.argv[2]), sys.argv[3])
