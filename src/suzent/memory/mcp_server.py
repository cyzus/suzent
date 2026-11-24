"""Serve Suzent's memory to other agents as an MCP server over stdio.

Claude Code, Codex, Cursor and other MCP clients start ``suzent mcp serve`` and
get three tools: search memory, read the user's profile, and (when the user has
allowed it) remember something. Like ``suzent acp`` this process is a translator,
not a second memory: every call goes to the running Suzent backend over the
loopback API, so one process stays the owner of the files and the index, and
nothing leaves the computer.
"""

from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field

from suzent.client.base import ClientError
from suzent.logger import get_logger

logger = get_logger(__name__)

SERVER_NAME = "suzent-memory"
SKILL_PATH = Path(__file__).parent / "agent_skill" / "SKILL.md"

INSTRUCTIONS = (
    "Long-term memory of the user, kept by their Suzent agent on this computer. "
    "Search it before asking the user something they may have told Suzent already, "
    "and read the profile at the start of work that depends on their preferences. "
    "When the user asks you to remember something, or you learn a lasting lesson, "
    "save it with memory_remember. Never save secrets or repository state."
)

PROFILE_BLOCKS = (("user", "About the user"), ("facts", "Key facts"))


def format_hits(memories: list[dict[str, Any]]) -> str:
    """Render search hits as a numbered list an agent can read."""
    if not memories:
        return "No relevant memories found."
    lines: list[str] = []
    for i, mem in enumerate(memories, 1):
        meta = mem.get("metadata") if isinstance(mem.get("metadata"), dict) else {}
        details = []
        kind = meta.get("kind")
        if kind:
            details.append(str(kind))
        stored = str(mem.get("created_at") or "")[:10]
        if stored:
            details.append(f"stored {stored}")
        source = meta.get("source_file")
        if source:
            details.append(f"from {source}")
        suffix = f"  ({', '.join(details)})" if details else ""
        lines.append(f"{i}. {mem.get('content', '')}{suffix}")
    return "\n".join(lines)


def format_profile(blocks: dict[str, str]) -> str:
    """The user and MEMORY.md blocks, without Suzent's own persona."""
    parts = [
        f"## {title}\n\n{blocks[label].strip()}"
        for label, title in PROFILE_BLOCKS
        if (blocks.get(label) or "").strip()
    ]
    return "\n\n".join(parts) or "No profile recorded yet."


class MemoryBridge:
    """The loopback calls the three tools need."""

    def __init__(self, base_url: str | None = None, agent: str | None = None):
        from suzent.client.api import SuzentAsyncClient

        self._client = SuzentAsyncClient(base_url)
        self.agent = agent

    @property
    def base_url(self) -> str:
        return self._client.base_url

    async def search(self, query: str, limit: int, kind: str | None) -> str:
        params: dict[str, Any] = {"query": query, "limit": limit}
        if kind:
            params["kinds"] = kind
        data = await self._client.get("/memory/archival", params=params)
        return format_hits(data.get("memories") or [])

    async def profile(self) -> str:
        data = await self._client.get("/memory/core")
        return format_profile(data.get("blocks") or {})

    async def remember(self, *, agent: str, **fields: Any) -> str:
        data = await self._client.post(
            "/memory/remember", json={**fields, "agent": self.agent or agent}
        )
        return f"Remembered: {data.get('written')}"

    async def aclose(self) -> None:
        await self._client.aclose()


def _client_name(ctx: Any) -> str:
    """The MCP client's own name from its initialize request, e.g. claude-code."""
    try:
        return ctx.session.client_params.clientInfo.name or ""
    except AttributeError:
        return ""


def build_server(bridge: MemoryBridge) -> Any:
    from mcp.server.fastmcp import Context, FastMCP

    server = FastMCP(SERVER_NAME, instructions=INSTRUCTIONS)

    @server.tool()
    async def memory_search(
        query: Annotated[
            str, Field(description="What to look for, in natural language.")
        ],
        limit: Annotated[int, Field(ge=1, le=20)] = 10,
        kind: Annotated[
            Literal["user", "experience", "world"] | None,
            Field(
                description=(
                    "user: about the user. experience: lessons from past work. "
                    "world: knowledge with its source. Omit to search everything."
                )
            ),
        ] = None,
    ) -> str:
        """Search the user's long-term memory by meaning, not exact words."""
        try:
            return await bridge.search(query, limit, kind)
        except ClientError as e:
            return f"Error: {e}"

    @server.tool()
    async def memory_profile() -> str:
        """Read what Suzent knows about the user: who they are, preferences, key facts."""
        try:
            return await bridge.profile()
        except ClientError as e:
            return f"Error: {e}"

    @server.tool()
    async def memory_remember(
        fact: Annotated[
            str,
            Field(
                description=(
                    "One sentence, subject first, e.g. 'User prefers pnpm over npm'. "
                    "No secrets, no repository state (versions, branches, PR numbers)."
                )
            ),
        ],
        ctx: Context,
        kind: Annotated[
            Literal["user", "experience", "world"],
            Field(
                description=(
                    "user: about the user, only what they said themselves. "
                    "experience: a lesson from how a task went. "
                    "world: how something works; put the path or URL in evidence."
                )
            ),
        ] = "user",
        category: Literal[
            "personal", "preference", "goal", "context", "technical"
        ] = "context",
        horizon: Annotated[
            Literal["durable", "dated"],
            Field(description="durable: true until changed. dated: will expire."),
        ] = "durable",
        evidence: Annotated[
            str,
            Field(
                description=(
                    "The user's exact words, the outcome, or the source path or URL."
                ),
                max_length=300,
            ),
        ] = "",
    ) -> str:
        """Save a memory to Suzent, marked as written by this agent.

        Use it when the user asks you to remember something, or when a task taught
        a lesson worth keeping. Suzent files it into the user's notes later.
        """
        try:
            return await bridge.remember(
                agent=_client_name(ctx),
                fact=fact,
                kind=kind,
                category=category,
                horizon=horizon,
                evidence=evidence,
            )
        except ClientError as e:
            return f"Error: {e}"

    return server


async def serve_stdio(*, base_url: str | None = None, agent: str | None = None) -> int:
    """Run the memory MCP server over stdin/stdout until the client disconnects."""
    from suzent.client.base import _is_loopback_url

    bridge = MemoryBridge(base_url, agent)
    if not _is_loopback_url(bridge.base_url):
        await bridge.aclose()
        logger.error("The memory MCP server only talks to a local Suzent backend")
        return 1
    logger.info(f"[memory-mcp] serving over stdio against {bridge.base_url}")
    try:
        await build_server(bridge).run_stdio_async()
    finally:
        await bridge.aclose()
    return 0
