"""Launch the locally installed Suzent as an Agent Client Protocol agent.

The ACP bridge talks to the Suzent backend over its private loopback API, so it
must ship with the backend it talks to. This package therefore carries no
bridge of its own: it finds the installed Suzent and hands the editor's pipes to
``suzent acp``. When Suzent is not installed it still answers the ACP handshake,
so an editor can show the sign-in choices and a clear install message.
"""

from importlib.metadata import PackageNotFoundError, version


def package_version() -> str:
    try:
        return version("suzent-acp")
    except PackageNotFoundError:
        return "0"
