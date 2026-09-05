"""Validated configuration and command boundary for managed browsing."""

import os
import re
import tempfile
from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from suzent.config.paths import DATA_DIR, USER_CONFIG_DIR


def normalize_browser_url(value: str) -> str:
    """Allow web navigation and an explicit empty page."""
    value = value.strip()
    if value == "about:blank":
        return value
    if not value or any(char.isspace() for char in value):
        raise ValueError("open requires a non-empty HTTP(S) URL")
    if "://" not in value:
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", value) and not re.match(
            r"^[^/:]+:\d+(?:/|$)", value
        ):
            raise ValueError("Only HTTP(S) URLs and about:blank are supported")
        value = "https://" + value
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only HTTP(S) URLs and about:blank are supported")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URLs must not contain credentials")
    _ = parsed.port
    return value


class BrowserPreferences(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    persistent: bool = False
    headless: bool = True
    channel: Literal["chromium", "chrome", "msedge"] = "chromium"

    def save(self) -> None:
        path = USER_CONFIG_DIR / "browser.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as file:
            temporary = Path(file.name)
            file.write(self.model_dump_json(indent=2))
        try:
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


class BrowserSettings(BrowserPreferences):
    model_config = ConfigDict(strict=False, extra="forbid")

    profile_dir: Path = Field(default_factory=lambda: DATA_DIR / "browser_profile")

    @classmethod
    def load(cls) -> Self:
        path = USER_CONFIG_DIR / "browser.json"
        saved = (
            BrowserPreferences.model_validate_json(path.read_text(encoding="utf-8"))
            if path.exists()
            else BrowserPreferences()
        )
        values = saved.model_dump()
        values.update(
            {
                key: os.environ[f"SUZENT_BROWSER_{key.upper()}"]
                for key in cls.model_fields
                if f"SUZENT_BROWSER_{key.upper()}" in os.environ
            }
        )
        return cls.model_validate(values)

    @classmethod
    def from_environment(cls) -> Self:
        values = {
            key: os.environ[f"SUZENT_BROWSER_{key.upper()}"]
            for key in cls.model_fields
            if f"SUZENT_BROWSER_{key.upper()}" in os.environ
        }
        return cls.model_validate(values)


class BrowserCommand(BaseModel):
    model_config = ConfigDict(strict=True)

    command: Literal[
        "open",
        "snapshot",
        "click",
        "dblclick",
        "hover",
        "fill",
        "type",
        "press",
        "back",
        "forward",
        "reload",
        "refresh",
        "click_coords",
        "scroll",
    ]
    arguments: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_arguments(self) -> Self:
        args = self.arguments
        match self.command:
            case "open":
                if len(args) > 1:
                    raise ValueError("open expects [url] or [] for about:blank")
                self.arguments = [
                    normalize_browser_url(args[0] if args else "about:blank")
                ]
            case "click" | "dblclick" | "hover" | "fill" | "type" | "press":
                count = 1 if self.command in {"click", "dblclick", "hover"} else 2
                syntax = "[ref]" if count == 1 else "[ref, value]"
                if len(args) != count:
                    raise ValueError(f"{self.command} expects {syntax}")
                if not re.fullmatch(r"@g\d+e\d+", args[0]):
                    raise ValueError(
                        "Use an exact ref from the latest snapshot, e.g. @g1e0"
                    )
                if self.command == "press" and not args[1]:
                    raise ValueError("press requires a non-empty key")
            case "click_coords" | "scroll":
                if self.command == "scroll" and not args:
                    self.arguments = ["0", "500"]
                elif len(args) != 2 or any(
                    not re.fullmatch(r"-?\d{1,6}", arg) for arg in args
                ):
                    raise ValueError(f"{self.command} expects two integer arguments")
                if self.command == "click_coords" and any(int(arg) < 0 for arg in args):
                    raise ValueError("click_coords requires non-negative coordinates")
            case "snapshot":
                if args == ["-i"]:
                    self.arguments = []
                elif len(args) > 2:
                    raise ValueError("snapshot expects [] or [offset, limit]")
                elif args:
                    if any(not re.fullmatch(r"\d{1,8}", arg) for arg in args):
                        raise ValueError("snapshot offset and limit must be integers")
                    if len(args) == 2 and not 1 <= int(args[1]) <= 100:
                        raise ValueError("snapshot limit must be between 1 and 100")
            case _:
                if args:
                    raise ValueError(f"{self.command} expects no arguments")
        return self
