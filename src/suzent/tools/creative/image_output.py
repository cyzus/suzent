"""Persist image endpoint results in the project library's artifacts/."""

import asyncio
import base64
from pathlib import Path
from uuid import uuid4

import aiohttp

from suzent.core.agent_deps import AgentDeps
from suzent.core.library_index import artifacts_dir, register_artifacts


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
    directory = artifacts_dir(deps, "images")
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
    saved = [str(path) for path in paths]
    register_artifacts(deps, saved, "generated image")
    return saved
