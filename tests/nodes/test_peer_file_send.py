from __future__ import annotations

import shutil
from pathlib import Path

import httpx
import pytest

from suzent.routes.suzent_channel_routes import (
    _download_peer_attachments,
    _validate_attachment_source,
)


def test_attachment_source_must_belong_to_authenticated_peer():
    with pytest.raises(ValueError, match="authenticated peer"):
        _validate_attachment_source(
            "http://169.254.169.254/nodes/peer-files/pf_123",
            "pf_123",
            client_host="192.168.1.10",
            callback_url="http://192.168.1.10:25314",
        )


@pytest.mark.asyncio
async def test_download_peer_attachment_to_staging_dir(monkeypatch):
    class FakeResponse:
        headers = {"content-length": "5"}

        def raise_for_status(self):
            return None

        async def aiter_bytes(self):
            yield b"hello"

    class StreamContext:
        async def __aenter__(self):
            return FakeResponse()

        async def __aexit__(self, *exc):
            return False

    class FakeClient:
        def __init__(self, *args, **kwargs):
            assert kwargs["follow_redirects"] is False
            assert kwargs["trust_env"] is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def stream(self, method, url, headers=None):
            assert method == "GET"
            assert url == "http://192.168.1.10:25314/nodes/peer-files/pf_123"
            assert headers == {"Authorization": "Bearer transfer-token"}
            return StreamContext()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    files, staging = await _download_peer_attachments(
        [
            {
                "id": "pf_123",
                "url": "http://192.168.1.10:25314/nodes/peer-files/pf_123",
                "token": "transfer-token",
                "name": "hello.txt",
                "media_type": "text/plain",
                "size": 5,
            }
        ],
        client_host="192.168.1.10",
        callback_url="http://192.168.1.10:25314",
    )

    try:
        assert staging is not None
        assert files[0]["filename"] == "hello.txt"
        assert files[0]["type"] == "file"
        assert Path(files[0]["path"]).read_bytes() == b"hello"
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)
