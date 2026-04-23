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
        self, node_id: str, command: str, params: dict | None = None
    ) -> dict:
        return await self.client.post(
            f"/nodes/{node_id}/invoke",
            json={"command": command, "params": params or {}},
        )


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

    async def enable(self, chat_id: str | None = None) -> dict:
        payload = {"chat_id": chat_id} if chat_id else {}
        return await self.client.post("/heartbeat/enable", json=payload)

    async def trigger(self, manual: bool = False, chat_id: str | None = None) -> dict:
        payload = {"manual": manual}
        if chat_id:
            payload["chat_id"] = chat_id
        return await self.client.post("/heartbeat", json=payload)

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

    async def approve_pairing(self, sender_id: str) -> dict:
        return await self.client.post(f"/social/pairing/{sender_id}/approve")

    async def deny_pairing(self, sender_id: str) -> dict:
        return await self.client.post(f"/social/pairing/{sender_id}/deny")


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


@lru_cache(maxsize=1)
def get_client() -> SuzentAsyncClient:
    return SuzentAsyncClient()
