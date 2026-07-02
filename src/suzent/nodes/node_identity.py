"""
Stable per-install node identity.

Each Suzent instance generates a persistent, self-assigned identity once and
reuses it across restarts. It is sent in grant-requests / peer-offers so the two
sides of a link can be matched on a value they *agree on* — unlike device_id /
peer_id (each side mints its own) or address (varies per network: LAN vs
Tailscale).

**This is an identifier, not an authenticator.** It is a plaintext label: a peer
could copy it to *claim* to be another device, but that grants no access —
authorization rides entirely on the per-grant bearer token, and pairing still
requires an operator's approval. See docs/02-concepts/nodes/security-plan.md for
the (deferred) cryptographic-identity option that would make it unspoofable.

Stored machine-locally (never synced), like device tokens and sandbox volumes.
"""

import json
import uuid

from suzent.config import USER_CONFIG_DIR
from suzent.logger import get_logger

logger = get_logger(__name__)

_PATH = USER_CONFIG_DIR / "node_identity.json"
_cached: str | None = None


def get_node_identity() -> str:
    """Return this install's stable node identity, generating it once if needed."""
    global _cached
    if _cached:
        return _cached
    try:
        if _PATH.exists():
            data = json.loads(_PATH.read_text() or "{}")
            nid = str(data.get("node_identity") or "").strip()
            if nid:
                _cached = nid
                return nid
    except Exception as e:
        logger.warning(f"Node identity: could not read {_PATH}: {e}")

    nid = uuid.uuid4().hex
    try:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        _PATH.write_text(json.dumps({"node_identity": nid}, indent=2))
    except Exception as e:
        logger.warning(f"Node identity: could not persist {_PATH}: {e}")
    _cached = nid
    return nid
