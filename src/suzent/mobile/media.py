"""Images, video, audio and files the agent made or sent in a conversation, as the phone sees them.

The phone names a file by an opaque id derived from its path, never by the path
itself. Only attachments and files reported by media tools in that conversation are served.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
from pathlib import PurePath
from typing import Literal

type MediaKind = Literal["image", "video", "audio", "file"]

MEDIA_TYPES: dict[str, tuple[MediaKind, str]] = {
    ".png": ("image", "image/png"),
    ".jpg": ("image", "image/jpeg"),
    ".jpeg": ("image", "image/jpeg"),
    ".gif": ("image", "image/gif"),
    ".webp": ("image", "image/webp"),
    ".mp4": ("video", "video/mp4"),
    ".mov": ("video", "video/quicktime"),
    ".m4v": ("video", "video/x-m4v"),
    ".webm": ("video", "video/webm"),
    ".mp3": ("audio", "audio/mpeg"),
    ".m4a": ("audio", "audio/mp4"),
    ".aac": ("audio", "audio/aac"),
    ".wav": ("audio", "audio/wav"),
    ".ogg": ("audio", "audio/ogg"),
    ".opus": ("audio", "audio/ogg"),
}

SAVED_PATH_TOOLS = {"generate_image", "edit_image", "check_video", "speak", "send_file"}
# Only send_file hands over arbitrary files; the others are media by construction.
ANY_FILE_TOOLS = {"send_file"}


def media_id(path: str) -> str:
    return hashlib.sha256(path.encode("utf-8")).hexdigest()[:32]


def media_type(path: str, any_file: bool = False) -> tuple[MediaKind, str] | None:
    known = MEDIA_TYPES.get(PurePath(path).suffix.lower())
    if known is None and any_file:
        guessed = mimetypes.guess_type(PurePath(path).name)[0]
        return "file", guessed or "application/octet-stream"
    return known


def _envelope(output: object) -> dict | None:
    current = output
    for _ in range(3):
        if isinstance(current, dict):
            return current
        if not isinstance(current, str):
            return None
        try:
            current = json.loads(current)
        except ValueError:
            return None
    return current if isinstance(current, dict) else None


def tool_media_paths(part: dict) -> list[str]:
    """Paths of the media a finished tool call produced or looked at."""
    name = part.get("toolName")
    if name not in SAVED_PATH_TOOLS and name != "analyze_visual":
        return []
    result = _envelope(part.get("output"))
    # A send_file whose chat-app upload failed still names files that exist here.
    if not result or (result.get("success") is not True and name not in ANY_FILE_TOOLS):
        return []
    metadata = result.get("metadata")
    if not isinstance(metadata, dict):
        return []
    raw = (
        metadata.get("saved_paths")
        if name in SAVED_PATH_TOOLS
        else [metadata.get("visual_path")]
    )
    if not isinstance(raw, list):
        return []
    any_file = name in ANY_FILE_TOOLS
    paths: list[str] = []
    for path in raw:
        if isinstance(path, str) and path.strip() and media_type(path, any_file):
            if path not in paths:
                paths.append(path)
    return paths


def media_items(part: dict) -> list[dict[str, str]]:
    any_file = part.get("toolName") in ANY_FILE_TOOLS
    return [
        {
            "id": media_id(path),
            "kind": media_type(path, any_file)[0],
            "name": PurePath(path).name,
        }
        for path in tool_media_paths(part)
    ]


def attachment_media(file: object) -> dict[str, str] | None:
    if not isinstance(file, dict):
        return None
    path = file.get("path")
    if not isinstance(path, str) or not path.strip():
        return None
    kind = media_type(path)
    if kind is None or kind[0] != "image":
        return None
    return {"id": media_id(path), "kind": kind[0], "name": PurePath(path).name}


def with_media(messages: list) -> list:
    """Messages with previews for uploaded images and media tool results."""
    annotated = []
    for message in messages:
        if isinstance(message, dict) and message.get("role") == "user":
            files = message.get("files")
            if isinstance(files, list):
                message = {
                    **message,
                    "files": [
                        {**file, "media": item}
                        if (item := attachment_media(file))
                        else file
                        for file in files
                    ],
                }
        parts = message.get("parts") if isinstance(message, dict) else None
        if not isinstance(parts, list):
            annotated.append(message)
            continue
        new_parts = []
        for part in parts:
            if isinstance(part, dict) and part.get("type") == "tool":
                if items := media_items(part):
                    part = {**part, "media": items}
            new_parts.append(part)
        annotated.append({**message, "parts": new_parts})
    return annotated


def find_media(messages: list, wanted: str) -> tuple[str, str] | None:
    """Resolve only files attached or reported by tools in these messages."""
    for message in messages:
        if isinstance(message, dict) and message.get("role") == "user":
            files = message.get("files")
            for file in files if isinstance(files, list) else []:
                if (item := attachment_media(file)) and item["id"] == wanted:
                    return file["path"], media_type(file["path"])[1]
        parts = message.get("parts") if isinstance(message, dict) else None
        for part in parts if isinstance(parts, list) else []:
            if not isinstance(part, dict) or part.get("type") != "tool":
                continue
            for path in tool_media_paths(part):
                if media_id(path) == wanted:
                    any_file = part.get("toolName") in ANY_FILE_TOOLS
                    return path, media_type(path, any_file)[1]
    return None
