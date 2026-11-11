"""Tests for the per-call usage logging proxy in examples/harbor."""

import importlib.util
import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

_PROXY_FILE = Path(__file__).parents[2] / "examples" / "harbor" / "usage_proxy.py"
_spec = importlib.util.spec_from_file_location("usage_proxy_under_test", _PROXY_FILE)
assert _spec and _spec.loader
usage_proxy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(usage_proxy)

_SSE = (
    b'data: {"choices":[{"delta":{"content":"Hi"}}]}\n\n'
    b'data: {"choices":[],"usage":{"prompt_tokens":9120,"completion_tokens":88,'
    b'"prompt_tokens_details":{"cached_tokens":8704}}}\n\n'
    b"data: [DONE]\n\n"
)


class _Upstream(BaseHTTPRequestHandler):
    seen: list[dict] = []

    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        _Upstream.seen.append(
            {"path": self.path, "body": body, "headers": dict(self.headers.items())}
        )
        if self.path.endswith("/broken"):
            self.send_response(429)
            self.end_headers()
            self.wfile.write(b'{"error":"slow down"}')
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        self.wfile.write(_SSE)

    do_GET = do_POST


def _serve(handler: type[BaseHTTPRequestHandler]) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture
def proxy(tmp_path: Path):
    _Upstream.seen = []
    upstream = _serve(_Upstream)
    log_path = tmp_path / "usage.jsonl"
    origin = f"http://127.0.0.1:{upstream.server_port}"
    server = _serve(usage_proxy.make_handler(origin, log_path))
    yield f"http://127.0.0.1:{server.server_port}", log_path
    server.shutdown()
    upstream.shutdown()


def _post(url: str, payload: dict) -> bytes:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Authorization": "Bearer stub", "Content-Type": "application/json"},
    )
    return urllib.request.urlopen(request, timeout=10).read()


def _records(log_path: Path) -> list[dict]:
    return [json.loads(line) for line in log_path.read_text().splitlines()]


def test_proxy_passes_the_stream_through_and_logs_its_usage(proxy):
    url, log_path = proxy

    body = _post(f"{url}/inference/v1/chat/completions", {"model": "kimi-k3"})

    assert body == _SSE
    seen = _Upstream.seen[0]
    assert seen["path"] == "/inference/v1/chat/completions"
    assert json.loads(seen["body"]) == {"model": "kimi-k3"}
    assert seen["headers"]["Authorization"] == "Bearer stub"
    [record] = _records(log_path)
    assert record["status"] == 200
    assert (record["prompt"], record["completion"], record["cached"]) == (
        9120,
        88,
        8704,
    )


def test_proxy_logs_one_line_per_completion_in_order(proxy):
    url, log_path = proxy

    for _ in range(3):
        _post(f"{url}/v1/chat/completions", {})

    assert len(_records(log_path)) == 3


def test_proxy_does_not_log_other_endpoints(proxy):
    url, log_path = proxy

    _post(f"{url}/v1/embeddings", {})

    assert not log_path.exists()


def test_proxy_relays_provider_errors_and_logs_them_without_usage(proxy):
    url, log_path = proxy

    with pytest.raises(urllib.error.HTTPError) as error:
        _post(f"{url}/v1/chat/completions/broken", {})

    assert error.value.code == 429
    [record] = _records(log_path)
    assert record["status"] == 429
    assert record["prompt"] is None


def test_proxy_answers_its_health_check_without_calling_upstream(proxy):
    url, _ = proxy

    reply = urllib.request.urlopen(f"{url}{usage_proxy.HEALTH_PATH}", timeout=5).read()

    assert reply == b"ok"
    assert _Upstream.seen == []
