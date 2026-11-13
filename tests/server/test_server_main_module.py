"""The server run as `python -m suzent.server` is the module routes import.

Routes import `suzent.server` lazily (to reload chat apps). If that import made
a second copy of the module, the copy held no social stack, so turning a chat
app off never stopped the one already polling.
"""

import subprocess
import sys

_PROBE = """
import asyncio, runpy, sys

def capture(coro):
    coro.close()
    with open(sys.argv[1], "w") as out:
        out.write(str(sys.modules.get("suzent.server") is sys.modules["__main__"]))

asyncio.run = capture
runpy.run_module("suzent.server", run_name="__main__", alter_sys=True)
"""


def test_running_server_is_the_imported_module(tmp_path, monkeypatch):
    monkeypatch.setenv("SUZENT_PORT", "0")
    result_file = tmp_path / "aliased.txt"
    subprocess.run(
        [sys.executable, "-c", _PROBE, str(result_file)],
        check=True,
        capture_output=True,
        timeout=120,
    )
    assert result_file.read_text() == "True"
