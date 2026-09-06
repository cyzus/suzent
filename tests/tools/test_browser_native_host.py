import io
import json
import struct
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

from suzent.config.paths import PROJECT_DIR

import pytest

from suzent.tools.browser.extension.native_host import serve
from suzent.tools.browser.extension import install


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native host launch")
async def test_browser_can_discover_changed_port_through_native_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import winreg
    from playwright.async_api import async_playwright, Error

    name = "com.suzent.test_" + uuid.uuid4().hex
    monkeypatch.setattr(install, "HOST_NAME", name)
    monkeypatch.setattr(install, "USER_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(install, "DATA_DIR", tmp_path)
    port_file = tmp_path / "runtime/server.port"
    port_file.parent.mkdir()
    assets = PROJECT_DIR / "extensions" / "browser"
    try:
        async with async_playwright() as playwright:
            try:
                browser = await playwright.chromium.launch_persistent_context(
                    str(tmp_path / "profile"),
                    channel="chromium",
                    headless=True,
                    args=[
                        f"--disable-extensions-except={assets}",
                        f"--load-extension={assets}",
                    ],
                )
            except Error as exc:
                if "Executable doesn't exist" in str(exc):
                    pytest.skip("Install Chromium for native messaging test")
                raise
            try:
                worker = (
                    browser.service_workers[0]
                    if browser.service_workers
                    else await browser.wait_for_event("serviceworker")
                )
                origin = worker.url.rsplit("/", 1)[0]
                install.install_native_host(origin)
                popup = await browser.new_page()
                await popup.goto(origin + "/popup.html")
                for port in [25314, 49322]:
                    port_file.write_text(str(port))
                    result = await popup.evaluate(
                        "name => chrome.runtime.sendNativeMessage(name, {action: 'endpoint'})",
                        name,
                    )
                    assert (
                        result["url"] == f"ws://127.0.0.1:{port}/ws/browser-extension"
                    )
            finally:
                await browser.close()
    finally:
        for vendor in ("Google\\Chrome", "Microsoft\\Edge"):
            try:
                winreg.DeleteKey(
                    winreg.HKEY_CURRENT_USER,
                    f"Software\\{vendor}\\NativeMessagingHosts\\{name}",
                )
            except FileNotFoundError:
                pass


@pytest.mark.parametrize("port", [25314, 49281])
def test_native_discovery_reads_current_port(tmp_path: Path, port: int) -> None:
    path = tmp_path / "server.port"
    path.write_text(str(port))
    body = json.dumps({"action": "endpoint"}).encode()
    response = io.BytesIO()
    serve(path, io.BytesIO(struct.pack("=I", len(body)) + body), response)
    data = response.getvalue()
    assert struct.unpack("=I", data[:4])[0] == len(data[4:])
    assert json.loads(data[4:])["url"] == f"ws://127.0.0.1:{port}/ws/browser-extension"


@pytest.mark.parametrize(
    "request_bytes", [b"", b"\xff" * 4, struct.pack("=I", 2) + b"{}"]
)
def test_native_discovery_rejects_other_requests(
    tmp_path: Path, request_bytes: bytes
) -> None:
    output = io.BytesIO()
    serve(tmp_path / "missing", io.BytesIO(request_bytes), output)
    assert not output.getvalue()


def test_windows_registration_is_per_user_and_origin_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = MagicMock()
    monkeypatch.setitem(__import__("sys").modules, "winreg", registry)
    monkeypatch.setattr(install.sys, "platform", "win32")
    monkeypatch.setattr(install, "USER_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(install, "DATA_DIR", tmp_path)
    origin = "chrome-extension://" + "a" * 32
    install.install_native_host(origin)
    manifest = json.loads((tmp_path / "browser-extension-host/host.json").read_text())
    assert manifest["allowed_origins"] == [origin + "/"]
    assert registry.CreateKey.call_count == 2
    assert all(
        call.args[0] == registry.HKEY_CURRENT_USER
        for call in registry.CreateKey.call_args_list
    )
    assert "server.port" in Path(manifest["path"]).read_text()


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_unix_host_manifests_are_scoped_to_browser_profiles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, platform: str
) -> None:
    monkeypatch.setattr(install.sys, "platform", platform)
    monkeypatch.setattr(install.Path, "home", lambda: tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.setattr(install, "USER_CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(install, "DATA_DIR", tmp_path)
    install.install_native_host("chrome-extension://" + "b" * 32)
    manifests = list(tmp_path.rglob("com.suzent.browser.json"))
    assert len(manifests) == (3 if platform == "linux" else 2)
    assert all(json.loads(path.read_text())["type"] == "stdio" for path in manifests)
