"""A minimal ACP agent for computers where Suzent is not installed.

It answers ``initialize`` with the same sign-in methods the real agent offers,
so an editor's agent list and the ACP Registry's checks see a well-formed
agent, and turns every other request into an install instruction.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any

from suzent_acp import package_version

PROTOCOL_VERSION = 1
METHOD_NOT_FOUND = -32601
INTERNAL_ERROR = -32603
TERMINAL_AUTH_ID = "suzent-terminal"
AGENT_AUTH_ID = "suzent-pair"
NOT_INSTALLED = (
    "Suzent is not installed on this computer. Install it from "
    "https://suzent.com, start it, then reconnect your editor."
)


def _client_name(params: dict[str, Any]) -> str:
    info = params.get("clientInfo")
    name = info.get("name") if isinstance(info, dict) else None
    if isinstance(name, str):
        name = " ".join(name.split())
        if 0 < len(name) <= 100:
            return name
    return "ACP client"


def initialize_result(params: dict[str, Any]) -> dict[str, Any]:
    """The handshake reply, mirroring the installed agent's sign-in methods."""
    capabilities = params.get("clientCapabilities")
    auth = capabilities.get("auth") if isinstance(capabilities, dict) else None
    methods: list[dict[str, Any]] = []
    if isinstance(auth, dict) and auth.get("terminal") is True:
        methods.append(
            {
                "id": TERMINAL_AUTH_ID,
                "type": "terminal",
                "name": "Pair with Suzent",
                "description": "Approve this editor in the local Suzent settings",
                "args": ["--login", "--client-name", _client_name(params)],
            }
        )
    methods.append(
        {
            "id": AGENT_AUTH_ID,
            "name": "Approve in Suzent settings",
            "description": "Open Settings → ACP Agents → Editor connections; compare the code in the agent log and approve the pending request.",
        }
    )
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "agentCapabilities": {
            "loadSession": False,
            "promptCapabilities": {
                "image": False,
                "audio": False,
                "embeddedContext": True,
            },
        },
        "authMethods": methods,
        "agentInfo": {"name": "suzent", "version": package_version()},
    }


def respond(message: Any) -> dict[str, Any] | None:
    """The reply to one decoded JSON-RPC message; notifications get none."""
    if not isinstance(message, dict) or "id" not in message:
        return None
    method = message.get("method")
    if method is None:
        return None
    params = message.get("params")
    params = params if isinstance(params, dict) else {}
    reply: dict[str, Any] = {"jsonrpc": "2.0", "id": message["id"]}
    if method == "initialize":
        reply["result"] = initialize_result(params)
    elif method in {
        "authenticate",
        "session/new",
        "session/load",
        "session/prompt",
    }:
        reply["error"] = {"code": INTERNAL_ERROR, "message": NOT_INSTALLED}
    else:
        reply["error"] = {
            "code": METHOD_NOT_FOUND,
            "message": f"unknown method '{method}'",
        }
    return reply


def serve(readline: Callable[[], str], write: Callable[[str], None]) -> None:
    """Answer newline-delimited JSON-RPC until the client closes the pipe."""
    while line := readline():
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            continue
        reply = respond(message)
        if reply is not None:
            write(json.dumps(reply, ensure_ascii=False, separators=(",", ":")) + "\n")


def serve_not_installed(argv: list[str]) -> int:
    if "--login" in argv:
        print(NOT_INSTALLED, file=sys.stderr)
        return 1
    if "--help" in argv or "-h" in argv:
        print(
            "Usage: suzent-acp [suzent acp options]\n\n"
            "Run by an ACP client. Starts the Suzent installed on this computer "
            "as its agent.\n\n" + NOT_INSTALLED,
            file=sys.stderr,
        )
        return 0
    print(NOT_INSTALLED, file=sys.stderr)

    # ACP frames are UTF-8 whatever the locale; a Windows code page stdout
    # cannot encode the "→" in the sign-in description.
    def readline() -> str:
        return sys.stdin.buffer.readline().decode("utf-8", "replace")

    def write(text: str) -> None:
        sys.stdout.buffer.write(text.encode("utf-8"))
        sys.stdout.buffer.flush()

    serve(readline, write)
    return 0
