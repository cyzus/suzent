"""The running server is the module that `import suzent.server` returns.

Routes import `suzent.server` lazily (to reload chat apps). If that import made
a second copy of the module, the copy held no social stack, so turning a chat
app off never stopped the one already polling. Both launch paths are covered:
`python -m suzent.server` and the OS service runner.
"""

import subprocess
import sys

import pytest

# Stub asyncio.run so the server stops right before serving, and record
# whether `suzent.server` resolves to the globals of the code that is running.
_CAPTURE = """
import asyncio, sys

def capture(coro):
    running_globals = coro.cr_frame.f_globals
    coro.close()
    imported = sys.modules.get("suzent.server")
    with open(sys.argv[1], "w") as out:
        out.write(str(imported is not None and imported.__dict__ is running_globals))

asyncio.run = capture
"""

_LAUNCHERS = {
    "python -m": 'import runpy\nrunpy.run_module("suzent.server", run_name="__main__", alter_sys=True)\n',
    "service": "from suzent.service.runtime import run_service\nrun_service()\n",
}


@pytest.mark.parametrize("launcher", sorted(_LAUNCHERS))
def test_running_server_is_the_imported_module(launcher, tmp_path, monkeypatch):
    monkeypatch.setenv("SUZENT_PORT", "0")
    # Its own data dir: the server writes a port file there, which later
    # tests in this session would otherwise read as the running server's port.
    monkeypatch.setenv("SUZENT_DATA_DIR", str(tmp_path / "data"))
    result_file = tmp_path / "aliased.txt"
    subprocess.run(
        [sys.executable, "-c", _CAPTURE + _LAUNCHERS[launcher], str(result_file)],
        check=True,
        capture_output=True,
        timeout=120,
    )
    assert result_file.read_text() == "True"
