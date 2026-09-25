"""Persist image endpoint results in the chat's shared workspace."""

import asyncio
import base64
from pathlib import Path
from uuid import uuid4

import aiohttp

from suzent.config import CONFIG
from suzent.core.agent_deps import AgentDeps


def image_suffix(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ".webp"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    raise ValueError("Image provider returned an unsupported image format.")


async def save_images(images: list[str], deps: AgentDeps) -> list[str]:
    if deps.chat_id:
        from suzent.database import get_database

        directory = get_database().get_project_dir(deps.chat_id) / "images"
    else:
        directory = Path(CONFIG.workspace_root) / "images"
    directory.mkdir(parents=True, exist_ok=True)
    payloads: list[tuple[bytes, str]] = []
    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=120)
    ) as session:
        for image in images:
            if image.startswith("data:"):
                header, encoded = image.split(",", 1)
                if not header.endswith(";base64"):
                    raise ValueError("Expected a base64 image response.")
                data = base64.b64decode(encoded, validate=True)
            else:
                async with session.get(image) as response:
                    response.raise_for_status()
                    data = await response.read()
            payloads.append((data, image_suffix(data)))
    paths: list[Path] = []
    try:
        for data, suffix in payloads:
            path = directory / f"image_{uuid4().hex}{suffix}"
            paths.append(path)
            await asyncio.to_thread(path.write_bytes, data)
    except Exception:
        for path in paths:
            path.unlink(missing_ok=True)
        raise
    return [str(path) for path in paths]
