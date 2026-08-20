"""
This device's A2A Agent Card — what outsiders discover about us.

The card is served unauthenticated at ``/.well-known/agent-card.json`` (the
spec's well-known path), so it is published only when the operator opts in via
``CONFIG.a2a_enabled``. It deliberately advertises the *agent*, not the node
mesh: node capabilities stay behind the authenticated node API, because A2A's
model is opaque execution while a node manifest is a transparent capability
surface. See docs/02-concepts/nodes/security.md.
"""

from __future__ import annotations

import platform
import socket

from suzent.a2a.types import (
    PROTOCOL_VERSION,
    TRANSPORT_JSONRPC,
    A2AModel,
)
from suzent.config import CONFIG
from suzent.nodes.node_identity import get_node_identity


class AgentSkill(A2AModel):
    id: str
    name: str
    description: str
    tags: list[str] = []
    examples: list[str] | None = None
    input_modes: list[str] | None = None
    output_modes: list[str] | None = None


class AgentCapabilities(A2AModel):
    streaming: bool = True
    push_notifications: bool = False
    state_transition_history: bool = False


class AgentProvider(A2AModel):
    organization: str
    url: str


class HTTPAuthSecurityScheme(A2AModel):
    type: str = "http"
    scheme: str = "bearer"
    description: str | None = None
    bearer_format: str | None = None


class AgentInterface(A2AModel):
    url: str
    transport: str


class AgentCard(A2AModel):
    protocol_version: str = PROTOCOL_VERSION
    name: str
    description: str
    url: str
    preferred_transport: str = TRANSPORT_JSONRPC
    additional_interfaces: list[AgentInterface] | None = None
    provider: AgentProvider | None = None
    version: str
    documentation_url: str | None = None
    capabilities: AgentCapabilities
    security_schemes: dict[str, HTTPAuthSecurityScheme] | None = None
    security: list[dict[str, list[str]]] | None = None
    default_input_modes: list[str]
    default_output_modes: list[str]
    skills: list[AgentSkill]
    supports_authenticated_extended_card: bool = False


def device_label() -> str:
    """Operator-set name, else the hostname — what a human recognizes."""
    configured = str(getattr(CONFIG, "a2a_agent_name", "") or "").strip()
    if configured:
        return configured
    try:
        return socket.gethostname() or "Suzent"
    except OSError:
        return "Suzent"


def os_environment() -> str:
    """Human-readable OS string, e.g. 'Windows 11 (AMD64)' or 'Darwin 24.3 (arm64)'.

    Surfaced on the card so a delegating agent can judge *where* it is sending
    work — the whole point of the mesh is that peers differ in capability, and
    'run this shell script' means something different per platform.
    """
    system = platform.system() or "Unknown"
    release = platform.release() or ""
    machine = platform.machine() or ""
    base = f"{system} {release}".strip()
    return f"{base} ({machine})" if machine else base


def _suzent_version() -> str:
    try:
        from importlib.metadata import version

        return version("suzent")
    except Exception:
        return "0.0.0"


def build_agent_card(base_url: str) -> AgentCard:
    """Construct the card for this device, served at the well-known path.

    ``base_url`` is the externally reachable origin (LAN or tailnet address),
    not necessarily what the request's Host header claims.
    """
    name = device_label()
    environment = os_environment()
    rpc_url = f"{base_url.rstrip('/')}/a2a/v1"

    return AgentCard(
        name=name,
        description=(
            f"Sovereign Suzent agent running on {environment}. "
            "Delegated work executes on this device, under its operator's rules."
        ),
        url=rpc_url,
        preferred_transport=TRANSPORT_JSONRPC,
        additional_interfaces=[
            AgentInterface(url=rpc_url, transport=TRANSPORT_JSONRPC)
        ],
        provider=AgentProvider(organization="Suzent", url="https://suzent.ai"),
        version=_suzent_version(),
        capabilities=AgentCapabilities(
            streaming=True,
            push_notifications=False,
            state_transition_history=False,
        ),
        security_schemes={
            "deviceGrant": HTTPAuthSecurityScheme(
                scheme="bearer",
                description=(
                    "A per-peer device grant token, issued by this device's "
                    "operator through the Suzent pairing flow."
                ),
            )
        },
        security=[{"deviceGrant": []}],
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[
            AgentSkill(
                id="chat",
                name="Converse and delegate",
                description=(
                    "Send this agent a task in natural language. It runs with "
                    f"the tools, files, and context available on {name} "
                    f"({environment}) and streams its reply back."
                ),
                tags=["chat", "delegation", "general"],
                examples=[
                    "Summarize the newest files in my downloads folder.",
                    "Run the test suite in ~/projects/api and report failures.",
                ],
                input_modes=["text/plain"],
                output_modes=["text/plain"],
            )
        ],
        # Identity is a label, not an authenticator (see node_identity docstring);
        # it lets a peer correlate this card with a device it already paired with.
        supports_authenticated_extended_card=False,
    )


def card_metadata() -> dict[str, str]:
    """Non-secret descriptors the UI shows next to the publish toggle."""
    return {
        "name": device_label(),
        "environment": os_environment(),
        "node_identity": get_node_identity(),
        "version": _suzent_version(),
    }
