"""Cross-device agent messaging over existing Suzent peer grants."""

from __future__ import annotations

from typing import Any

import httpx

from suzent.nodes.peer_store import PeerGrantStore, get_peer_grant_store

REMOTE_AGENT_PREFIX = "peer:"
_REQUEST_TIMEOUT_SECONDS = 15.0


class PeerAgentTransportError(RuntimeError):
    """Raised when a peer address or delivery cannot be used."""


class PeerAgentTransport:
    """Adapter between durable agent messages and paired Suzent backends."""

    def __init__(self, store: PeerGrantStore):
        self.store = store

    @staticmethod
    def agent_id(peer_id: str) -> str:
        return f"{REMOTE_AGENT_PREFIX}{peer_id}"

    @staticmethod
    def peer_id(agent_id: str) -> str | None:
        if not agent_id.startswith(REMOTE_AGENT_PREFIX):
            return None
        peer_id = agent_id.removeprefix(REMOTE_AGENT_PREFIX).strip()
        return peer_id or None

    def list_agents(self) -> list[dict[str, Any]]:
        """Expose controllable peers as stable remote agent addresses."""
        return [
            {
                "agent_id": self.agent_id(peer["peer_id"]),
                "title": peer.get("name") or peer.get("base_url") or "Remote agent",
                "kind": "remote",
                "status": (
                    "ready" if peer.get("mode", "trigger") == "trigger" else "paused"
                ),
                "project_id": None,
                "parent_agent_id": None,
                "updated_at": peer.get("added_at") or None,
                "peer_id": peer["peer_id"],
            }
            for peer in self.store.list_peers()
        ]

    def resolve(self, agent_id: str, *, require_enabled: bool = True) -> dict[str, Any]:
        peer_id = self.peer_id(agent_id)
        peer = self.store.get(peer_id or "") if peer_id else None
        if peer is None:
            raise PeerAgentTransportError(f"Unknown remote agent '{agent_id}'")
        if require_enabled and peer.get("mode", "trigger") != "trigger":
            raise PeerAgentTransportError(f"Remote agent '{agent_id}' is paused")
        return {**peer, "peer_id": peer_id, "agent_id": agent_id}

    def enqueue(
        self, *, agent_id: str, sender_chat_id: str, content: str
    ) -> tuple[dict[str, Any], bool]:
        """Persist an outbound peer message without performing network I/O."""
        peer = self.resolve(agent_id)
        from suzent.core.agent_inbox import enqueue_agent_message

        return enqueue_agent_message(
            sender_chat_id=sender_chat_id,
            target_chat_id=agent_id,
            content=content,
            transport="suzent_peer",
            destination_peer_id=peer["peer_id"],
            kind="remote_agent_message",
            max_attempts=48,
        )

    async def _request(
        self,
        peer: dict[str, Any],
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Issue one authenticated request through the shared peer grant."""
        try:
            async with httpx.AsyncClient(
                timeout=_REQUEST_TIMEOUT_SECONDS, trust_env=False
            ) as client:
                return await client.request(
                    method,
                    f"{peer['base_url']}{path}",
                    headers={"Authorization": f"Bearer {peer['token']}"},
                    json=json,
                )
        except httpx.HTTPError as exc:
            raise PeerAgentTransportError(
                f"Could not reach remote agent: {type(exc).__name__}"
            ) from exc

    async def deliver(self, message: dict[str, Any]) -> None:
        """Deliver one leased outbox row; remote persistence is the ACK."""
        peer_id = str(message.get("destination_peer_id") or "")
        peer = self.resolve(self.agent_id(peer_id))
        response = await self._request(
            peer,
            "POST",
            "/channels/suzent/inbox",
            json={
                "message_id": message["message_id"],
                "content": message["content"],
            },
        )
        if response.status_code != 202:
            raise PeerAgentTransportError(
                f"Peer rejected inbox message with HTTP {response.status_code}"
            )
        try:
            acknowledgment = response.json()
        except ValueError as exc:
            raise PeerAgentTransportError("Peer returned an invalid inbox ACK") from exc
        if not acknowledgment.get("accepted") or acknowledgment.get(
            "message_id"
        ) != str(message["message_id"]):
            raise PeerAgentTransportError("Peer returned a mismatched inbox ACK")

    async def read(self, agent_id: str) -> dict[str, Any]:
        """Read the transcript dedicated to this authenticated peer relationship."""
        peer = self.resolve(agent_id)
        response = await self._request(peer, "GET", "/channels/suzent/session")
        if response.status_code != 200:
            raise PeerAgentTransportError(
                f"Peer session read failed with HTTP {response.status_code}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise PeerAgentTransportError(
                "Peer returned an invalid session response"
            ) from exc
        if not isinstance(payload, dict):
            raise PeerAgentTransportError("Peer returned an invalid session response")
        return payload

    async def stop(self, agent_id: str) -> bool:
        """Request cooperative cancellation of this peer's dedicated agent session."""
        peer = self.resolve(agent_id)
        response = await self._request(peer, "POST", "/channels/suzent/stop")
        if response.status_code == 409:
            return False
        if response.status_code != 200:
            raise PeerAgentTransportError(
                f"Peer stop failed with HTTP {response.status_code}"
            )
        return True


_transport: PeerAgentTransport | None = None


def get_peer_agent_transport() -> PeerAgentTransport:
    global _transport
    store = get_peer_grant_store()
    if _transport is None or _transport.store is not store:
        _transport = PeerAgentTransport(store)
    return _transport
