from functools import lru_cache

from suzent.client.base import AsyncBaseClient


class NodesAPI:
    def __init__(self, client: AsyncBaseClient):
        self.client = client

    async def list(self) -> dict:
        return await self.client.get("/nodes")

    async def describe(self, node_id: str) -> dict:
        return await self.client.get(f"/nodes/{node_id}")

    async def invoke(
        self,
        node_id: str,
        command: str,
        params: dict | None = None,
        timeout: float | None = None,
    ) -> dict:
        body: dict = {"command": command, "params": params or {}}
        if timeout is not None:
            body["timeout"] = timeout
        return await self.client.post(f"/nodes/{node_id}/invoke", json=body)

    async def pending(self) -> dict:
        return await self.client.get("/nodes/pending")

    async def approve(self, pairing_code: str) -> dict:
        return await self.client.post(f"/nodes/pending/{pairing_code}/approve")

    async def deny(self, pairing_code: str) -> dict:
        return await self.client.post(f"/nodes/pending/{pairing_code}/deny")

    async def devices(self) -> dict:
        return await self.client.get("/nodes/devices")

    async def revoke(self, device_id: str) -> dict:
        return await self.client.post(f"/nodes/devices/{device_id}/revoke")

    async def discover(self, timeout: float | None = None) -> dict:
        path = "/nodes/discover"
        if timeout is not None:
            path += f"?timeout={timeout}"
        return await self.client.get(path)

    async def connect(self, gateway_url: str, name: str = "") -> dict:
        return await self.client.post(
            "/nodes/connect",
            json={"gateway_url": gateway_url, "name": name},
        )

    async def connections(self) -> dict:
        return await self.client.get("/nodes/connections")

    async def disconnect(self, gateway_url: str) -> dict:
        return await self.client.post(
            "/nodes/connect/stop", json={"gateway_url": gateway_url}
        )

    # Control-grant peers (devices this one can drive over HTTP)
    async def peers(self) -> dict:
        return await self.client.get("/nodes/peers")

    async def peer_capabilities(self, peer_id: str) -> dict:
        return await self.client.get(f"/nodes/peers/{peer_id}/capabilities")

    async def grants(self) -> dict:
        return await self.client.get("/nodes/grants")

    async def remove_peer(self, peer_id: str) -> dict:
        return await self.client.post(f"/nodes/peers/{peer_id}/remove")

    async def set_peer_mode(self, peer_id: str, mode: str) -> dict:
        return await self.client.post(
            f"/nodes/peers/{peer_id}/mode", json={"mode": mode}
        )

    async def invoke_peer(
        self,
        peer_id: str,
        command: str,
        params: dict | None = None,
        timeout: float | None = None,
    ) -> dict:
        body: dict = {"command": command, "params": params or {}}
        if timeout is not None:
            body["timeout"] = timeout
        return await self.client.post(f"/nodes/peers/{peer_id}/invoke", json=body)

    async def trigger(self, peer_id: str, prompt: str, chat_id: str | None = None):
        """Stream a peer agent run; yields raw SSE chunks (bytes)."""
        payload: dict = {"prompt": prompt}
        if chat_id:
            payload["chat_id"] = chat_id
        async for chunk in self.client.stream_post(
            f"/nodes/peers/{peer_id}/trigger", json=payload, timeout=None
        ):
            yield chunk


class CronAPI:
    def __init__(self, client: AsyncBaseClient):
        self.client = client

    async def list_jobs(self) -> dict:
        return await self.client.get("/cron/jobs")

    async def create_job(self, payload: dict) -> dict:
        return await self.client.post("/cron/jobs", json=payload)

    async def update_job(self, job_id: int, updates: dict) -> dict:
        return await self.client.put(f"/cron/jobs/{job_id}", json=updates)

    async def delete_job(self, job_id: int) -> dict:
        return await self.client.delete(f"/cron/jobs/{job_id}")

    async def trigger_job(self, job_id: int) -> dict:
        return await self.client.post(f"/cron/jobs/{job_id}/trigger")

    async def job_history(self, job_id: int, limit: int = 10) -> dict:
        return await self.client.get(f"/cron/jobs/{job_id}/runs?limit={limit}")

    async def status(self) -> dict:
        return await self.client.get("/cron/status")

    async def install_presets(self, activate_existing: bool) -> dict:
        return await self.client.post(
            "/cron/presets/install", json={"activate_existing": activate_existing}
        )


class HeartbeatAPI:
    def __init__(self, client: AsyncBaseClient):
        self.client = client

    async def status(self, chat_id: str | None = None) -> dict:
        params = {"chat_id": chat_id} if chat_id else None
        return await self.client.get("/heartbeat/status", params=params)

    async def enable(self, chat_id: str | None = None) -> dict:
        payload = {"chat_id": chat_id} if chat_id else {}
        return await self.client.post("/heartbeat/enable", json=payload)

    async def disable(self, chat_id: str | None = None) -> dict:
        payload = {"chat_id": chat_id} if chat_id else {}
        return await self.client.post("/heartbeat/disable", json=payload)

    async def trigger(self, manual: bool = False, chat_id: str | None = None) -> dict:
        payload = {"manual": manual}
        if chat_id:
            payload["chat_id"] = chat_id
        return await self.client.post("/heartbeat/trigger", json=payload)

    async def update_interval(self, payload: dict) -> dict:
        return await self.client.post("/heartbeat/interval", json=payload)


class ConfigAPI:
    def __init__(self, client: AsyncBaseClient):
        self.client = client

    async def get(self) -> dict:
        return await self.client.get("/config")

    async def update_preferences(self, updates: dict) -> dict:
        return await self.client.post("/preferences", json=updates)


class SocialAPI:
    def __init__(self, client: AsyncBaseClient):
        self.client = client

    async def pending_pairings(self) -> dict:
        return await self.client.get("/social/pairing")

    async def approve_pairing_by_token(self, token: str) -> dict:
        return await self.client.post("/social/pairing/approve", json={"token": token})

    async def deny_pairing_by_token(self, token: str) -> dict:
        return await self.client.post("/social/pairing/deny", json={"token": token})


class MCPAPI:
    def __init__(self, client: AsyncBaseClient):
        self.client = client

    async def list(self) -> dict:
        """Returns four parallel dicts keyed by name: urls, stdio, headers, enabled."""
        return await self.client.get("/mcp_servers")

    async def add(
        self,
        name: str,
        *,
        url: str | None = None,
        headers: dict | None = None,
        stdio: dict | None = None,
    ) -> dict:
        payload: dict = {"name": name}
        if url:
            payload["url"] = url
            if headers:
                payload["headers"] = headers
        if stdio:
            payload["stdio"] = stdio
        return await self.client.post("/mcp_servers", json=payload)

    async def update(
        self,
        name: str,
        *,
        url: str | None = None,
        headers: dict | None = None,
        stdio: dict | None = None,
    ) -> dict:
        payload: dict = {"name": name}
        if url:
            payload["url"] = url
            if headers:
                payload["headers"] = headers
        if stdio:
            payload["stdio"] = stdio
        return await self.client.post("/mcp_servers/update", json=payload)

    async def remove(self, name: str) -> dict:
        return await self.client.post("/mcp_servers/remove", json={"name": name})

    async def test(self, name: str) -> dict:
        """Probe a configured server: {ok, tools} or {ok: False, error}."""
        return await self.client.post("/mcp_servers/test", json={"name": name})

    async def set_enabled(self, name: str, enabled: bool) -> dict:
        return await self.client.post(
            "/mcp_servers/enabled", json={"name": name, "enabled": enabled}
        )


class SkillsAPI:
    def __init__(self, client: AsyncBaseClient):
        self.client = client

    async def list(self) -> list:
        """Returns a list of {name, description, path, source, enabled}."""
        return await self.client.get("/skills")

    async def toggle(self, name: str) -> dict:
        return await self.client.post(f"/skills/{name}/toggle")

    async def reload(self) -> list:
        return await self.client.post("/skills/reload")


class ChatAPI:
    def __init__(self, client: AsyncBaseClient):
        self.client = client

    async def commands(self, surface: str = "cli") -> dict:
        return await self.client.get(f"/commands?surface={surface}")

    async def get_chat(self, chat_id: str) -> dict:
        return await self.client.get(f"/chats/{chat_id}")

    async def create_chat(self, payload: dict) -> dict:
        return await self.client.post("/chats", json=payload)

    async def stream_message(self, payload: dict):
        async for chunk in self.client.stream_post("/chat", json=payload):
            yield chunk


class SuzentAsyncClient(AsyncBaseClient):
    def __init__(self, base_url: str | None = None):
        super().__init__(base_url)
        self.nodes = NodesAPI(self)
        self.cron = CronAPI(self)
        self.heartbeat = HeartbeatAPI(self)
        self.config = ConfigAPI(self)
        self.social = SocialAPI(self)
        self.chat = ChatAPI(self)
        self.mcp = MCPAPI(self)
        self.skill = SkillsAPI(self)


@lru_cache(maxsize=1)
def get_client() -> SuzentAsyncClient:
    return SuzentAsyncClient()
